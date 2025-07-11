import builtins
import datetime
import json
import logging
import re
import uuid
from copy import copy
from decimal import Decimal
from random import choice
from typing import Any, Dict, List, Optional, Tuple, Type
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin, UserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields.array import ArrayField
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import RegexValidator
from django.db import connection, models, transaction
from django.db.models import Case, ExpressionWrapper, F, Q, QuerySet, When
from django.db.models.aggregates import Sum
from django.db.models.fields import DateTimeField, DurationField
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_text
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.timesince import timesince as djtimesince
from django.utils.translation import ugettext_lazy as _

import architect
import short_url
import tldextract
from creditcards.models import CardNumberField
from creditcards.types import CC_TYPE_CHOICES, CC_TYPE_GENERIC, CC_TYPES
from creditcards.utils import get_digits
from django_cryptography.fields import encrypt
from django_fsm import ConcurrentTransitionMixin, FSMIntegerField, transition
from facebook_business import FacebookAdsApi
from facebook_business.adobjects.business import Business
from faker import Faker
from imagekit.models import ImageSpecField, ProcessedImageField
from model_utils import FieldTracker
from pilkit.processors import ResizeToFill, Transpose
from redis import Redis

FacebookAdsApi.HTTP_DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/80.0.3987.87 Safari/537.36'
}

PHONE_REGEX = RegexValidator(
    regex=r'^\+?1?\d{9,15}$',
    message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.",
)
redis = Redis(host='redis', db=0, decode_responses=True)

logger = logging.getLogger(__name__)


def default_paid_till():
    paid_till = timezone.now() + datetime.timedelta(days=8)  # 7 дней в бОльшую сторону
    return paid_till.replace(hour=0, minute=0, second=0, microsecond=0)


class LogChangedMixin(models.Model):
    fieldtracker = FieldTracker()

    def get_changed_data(self):
        changed_data: List[Dict[str, Any]] = []
        for field, original in self.fieldtracker.changed().items():
            changed_data.append(
                {
                    'field_name': self._meta.get_field(field).verbose_name.title(),
                    'field': field,
                    'old': original,
                    'new': getattr(self, field),
                }
            )
        return changed_data

    class Meta:
        abstract = True


class Country(models.Model):
    name = models.CharField(max_length=64)
    code = models.CharField(max_length=2)
    is_public = models.BooleanField(default=False)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('sort',)
        verbose_name = 'Country'
        verbose_name_plural = 'Countries'

    def __str__(self):
        return self.name


class ShortifyDomain(models.Model):
    domain = models.CharField(max_length=128)
    is_public = models.BooleanField(default=False)
    is_banned = models.BooleanField(default=False)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('sort',)
        verbose_name = 'Shortify Domain'
        verbose_name_plural = 'Shortify Domains'

    def __str__(self):
        return self.domain


class PageCategory(models.Model):
    name = models.CharField(max_length=128)
    fb_id = models.BigIntegerField(_('FB ID'))
    is_public = models.BooleanField(default=False)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('sort',)
        verbose_name = 'PageCategory'
        verbose_name_plural = 'PageCategories'

    def __str__(self):
        return self.name


class Config(models.Model):
    """
    Модель для хранения некоторых глобальных настроек,
    которые в процессе работы могут изменяться
    """

    TYPE_CHOICES = (
        ('str', _('String')),
        ('float', _('Float')),
        ('int', _('Integer')),
        ('dict', _('Dict')),
        ('bool', _('Boolean')),
    )

    key = models.SlugField(_('Setting key'), max_length=32, unique=True, db_index=True)
    value = models.TextField(_('Setting value'))
    value_type = models.CharField(_('Value type'), max_length=10, choices=TYPE_CHOICES, default='str')
    verbose_name = models.CharField(_('Verbose name'), max_length=64, null=True, blank=True)
    description = models.CharField(_('Usefull description'), max_length=255, null=True, blank=True)
    updated = models.DateTimeField(_('Updated'), auto_now=True)
    is_active = models.BooleanField(_('Is active'), default=True)

    @classmethod
    def get_value(cls, key):
        return cls.objects.get(key=key, is_active=True).typed_value

    @cached_property
    def typed_value(self):
        if self.value_type == 'dict':
            return json.loads(self.value)
        return getattr(builtins, self.value_type, None)(self.value)

    def __str__(self):
        return '{} - {}'.format(self.verbose_name, self.key)

    class Meta:
        verbose_name = _('Config')
        verbose_name_plural = _('Config')


class Team(models.Model):
    name = models.CharField(_('Command name'), max_length=255)
    description = models.CharField(_('Command description'), max_length=255)

    def __str__(self):
        return self.name


class Tag(models.Model):
    # user = models.ForeignKey('User', on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=64, unique=True, db_index=True)

    def __str__(self):
        return self.name


# https://github.com/jazzband/django-model-utils/issues/331
# delete the shadowed attribute
del AbstractBaseUser.is_active  # type: ignore


class User(LogChangedMixin, AbstractBaseUser, PermissionsMixin):
    # User role
    ADMIN = 0
    MEDIABUYER = 10
    FINANCIER = 20
    FARMER = 30
    SUPPLIER = 40
    SETUPER = 50
    MANAGER = 60
    TEAMLEAD = 70
    SUPPLIER_TEAMLEAD = 80
    JUNIOR = 90

    USER_ROLE_CHOICES = (
        (ADMIN, _('Admin')),
        (MEDIABUYER, _('Mediabuyer')),
        (FINANCIER, _('Financier')),
        (FARMER, _('Farmer')),
        (SUPPLIER, _('Supplier')),
        (SUPPLIER_TEAMLEAD, _('Supplier Teamlead')),
        (SETUPER, _('Setuper')),
        (MANAGER, _('Manager')),
        (TEAMLEAD, _('Teamlead')),
        (JUNIOR, _('Junior')),
    )

    username_validator = UnicodeUsernameValidator()

    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        help_text=_('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        validators=[username_validator],
        error_messages={'unique': _("A user with that username already exists.")},
    )
    first_name = models.CharField(_('first name'), max_length=30, null=True, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, null=True, blank=True)
    email = models.EmailField(_('email address'), null=True, blank=True)
    is_staff = models.BooleanField(_('staff status'), default=False)
    is_active = models.BooleanField(_('Is active'), default=True)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    role = models.PositiveSmallIntegerField(_('User role'), choices=USER_ROLE_CHOICES, default=10)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)

    profit_target = models.DecimalField(_('Monthly Profit target'), decimal_places=2, max_digits=10, default=0)

    # Telegram data
    telegram_id = models.BigIntegerField(null=True, blank=True)
    photo_url = models.URLField(null=True, blank=True, max_length=1024)

    # Tracker Credentials
    tracker_type = models.CharField(_('Трекер'), default='zeustrak', max_length=32, null=True, blank=True)
    tracker_login = models.CharField(max_length=255, null=True, blank=True)
    tracker_password = models.CharField(max_length=255, null=True, blank=True)

    mla_login = models.CharField(max_length=255, null=True, blank=True)
    mla_group_id = models.UUIDField(null=True, blank=True)

    proxy_host = models.CharField(max_length=128, null=True, blank=True)
    proxy_port = models.PositiveIntegerField(null=True, blank=True)
    proxy_login = models.CharField(max_length=64, null=True, blank=True)
    proxy_password = models.CharField(max_length=64, null=True, blank=True)

    objects = UserManager()
    fieldtracker = FieldTracker()

    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        ordering = ('-date_joined',)

    def __str__(self):
        return f'User: {self.display_name}'

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name

    @property
    def full_name(self):
        return self.get_full_name()

    @property
    def display_name(self):
        return self.get_full_name() if self.first_name and self.last_name else self.username

    # TODO: cache
    @cached_property
    def banned_accounts(self):
        return self.managing_accounts.filter(status=Account.BANNED).count()

    # TODO: cache
    @cached_property
    def onverify_accounts(self):
        return self.managing_accounts.filter(status=Account.ON_VERIFY).count()

    # TODO: cache
    @cached_property
    def active_accounts(self):
        return self.managing_accounts.filter(status=Account.ACTIVE).count()

    @classmethod
    def get_recipients(cls, roles: List[int]):
        return cls.objects.filter(role__in=roles, is_active=True)

    @classmethod
    @transaction.atomic
    def create(cls, actor: Any, username: str, password: str, role: int, **kwargs):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        user = cls(username=username, role=role, date_joined=now, **kwargs)
        user.set_password(password)
        user.save()

        action_data = {'username': username, 'role': role}
        team = kwargs.pop('team', None)
        if team:
            action_data['team'] = {'id': team.id, 'name': team.name}

        action_data.update(**kwargs)
        Action.create(actor=actor, action_datetime=now, verb='created', action_object=user, data=action_data)
        return user

    @classmethod
    @transaction.atomic
    def update(cls, actor: Any, pk: int, **kwargs):
        assert 'password' not in kwargs  # Смена пароля отдельным методом
        # TODO: дропать токен и разлогинивать
        # if 'is_active' in kwargs:
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        user = cls.objects.select_for_update().get(id=pk)
        for field_name, value in kwargs.items():
            setattr(user, field_name, value)

        changed_data = user.get_changed_data()
        if changed_data:
            user.save()
            Action.create(actor=actor, action_datetime=now, verb='updated user', action_object=user, data=changed_data)
        return user

    @classmethod
    @transaction.atomic
    def connect_telegram(cls, pk: int, telegram_id=int, photo_url: Optional[str] = None):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        user = cls.objects.select_for_update().get(id=pk)
        user.telegram_id = telegram_id
        user.photo_url = photo_url
        changed_data = user.get_changed_data()
        if changed_data:
            user.save(update_fields=['telegram_id', 'photo_url'])
            Action.create(
                actor=user, action_datetime=now, verb='connected telegram', action_object=user, data=changed_data
            )
            from core.tasks.notifications import send_welcome_message

            send_welcome_message.delay(user.telegram_id)

        return user

    @classmethod
    @transaction.atomic
    def update_password(cls, actor: Any, pk: int, password: str):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        user = cls.objects.select_for_update().get(id=pk)
        user.set_password(password)
        user.save(update_fields=['password'])
        Action.create(actor=actor, action_datetime=now, verb='changed password', action_object=user)
        return user


class FieldsSetting(models.Model):
    # ACTION_CHOICE = (('list', 'list'), ('retrieve', 'retrieve'), ('edit', 'edit'))
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    slug = models.CharField(max_length=255)
    # action = models.CharField(max_length=32, choices=ACTION_CHOICE, default='list')
    fields = ArrayField(base_field=models.CharField(max_length=32))

    class Meta:
        unique_together = ('user', 'slug')


@architect.install('partition', type='range', subtype='date', constraint='month', column='action_datetime')
class Action(models.Model):
    """
    Action model describing the actor (optional) acting out a verb (on an optional
    target).
    Nomenclature based on http://activitystrea.ms/specs/atom/1.0/
    Generalized Format::
        <actor> <verb> <time>
        <actor> <verb> <target> <time>
        <actor> <verb> <action_object> <target> <time>
    Examples::
        <justquick> <reached level 60> <1 minute ago>
        <brosner> <commented on> <pinax/pinax> <2 hours ago>
        <washingtontimes> <started follow> <justquick> <8 minutes ago>
        <mitsuhiko> <closed> <issue 70> on <mitsuhiko/flask> <about 2 hours ago>
    Unicode Representation::
        justquick reached level 60 1 minute ago
        mitsuhiko closed issue 70 on mitsuhiko/flask 3 hours ago
    HTML Representation::
        <a href="http://oebfare.com/">brosner</a> commented on
        <a href="http://github.com/pinax/pinax">pinax/pinax</a> 2 hours ago
    """

    actor = models.ForeignKey(User, models.PROTECT, null=True, blank=True)

    verb = models.CharField(max_length=255, db_index=True)
    verb_slug = models.SlugField(max_length=255, db_index=True)

    action_object_content_type = models.ForeignKey(
        ContentType, blank=True, null=True, related_name='action_object', on_delete=models.PROTECT, db_index=True
    )
    action_object_object_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    action_object = GenericForeignKey('action_object_content_type', 'action_object_object_id')
    action_object_repr = models.CharField(
        _('Action object repr'), max_length=255, blank=True, null=True, db_index=True
    )

    target_object_content_type = models.ForeignKey(
        ContentType, blank=True, null=True, related_name='target_object', on_delete=models.PROTECT, db_index=True
    )
    target_object_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    target_object = GenericForeignKey('target_object_content_type', 'target_object_id')
    target_object_repr = models.CharField(_('Target repr'), max_length=255, blank=True, null=True, db_index=True)

    action_datetime = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    data = models.JSONField(_('Additional action data'), encoder=DjangoJSONEncoder, null=True, blank=True)

    class Meta:
        # ordering = ('-action_datetime',)
        index_together = (
            ('action_object_content_type', 'action_object_object_id'),
            ('target_object_content_type', 'target_object_id'),
            (
                'action_object_content_type',
                'action_object_object_id',
                'target_object_content_type',
                'target_object_id',
            ),
        )

    def __str__(self):
        ctx = {
            'actor': self.actor,
            'verb': self.verb,
            'action_object_repr': self.action_object_repr,
            'target_object_repr': self.target_object_repr,
            'timesince': self.timesince(),
        }
        if self.target_object:
            if self.action_object:
                return _('%(actor)s %(verb)s %(action_object_repr)s on %(target_object_repr)s %(timesince)s ago') % ctx
            return _('%(actor)s %(verb)s %(action_object_repr)s %(timesince)s ago') % ctx
        if self.action_object:
            return _('%(actor)s %(verb)s %(action_object_repr)s %(timesince)s ago') % ctx
        return _('%(actor)s %(verb)s %(timesince)s ago') % ctx

    def timesince(self, now=None):
        """
        Shortcut for the ``django.utils.timesince.timesince`` function of the
        current timestamp.
        """
        return djtimesince(self.action_datetime, now).encode('utf8').replace(b'\xc2\xa0', b' ').decode('utf8')

    @classmethod
    @transaction.atomic
    def create(cls, action_datetime, verb, actor=None, target_object=None, action_object=None, data=None):
        action_data = {'action_datetime': action_datetime, 'verb': verb, 'verb_slug': slugify(verb)}
        if target_object is not None:
            action_data['target_object_content_type'] = ContentType.objects.get_for_model(target_object)
            action_data['target_object_id'] = target_object.id
            action_data['target_object_repr'] = force_text(target_object)

        if action_object is not None:
            action_data['action_object_content_type'] = ContentType.objects.get_for_model(action_object)
            action_data['action_object_object_id'] = action_object.id
            action_data['action_object_repr'] = force_text(action_object)

        if data is not None:
            action_data['data'] = data

        if actor is not None:
            action_data['actor_id'] = actor.id

        return cls.objects.create(**action_data)


class Account(ConcurrentTransitionMixin, LogChangedMixin):
    # ACCOUNT_STATUS_CHOICES
    ACTIVE = 0
    LOGOUT = 10
    BANNED = 20
    ON_VERIFY = 30
    INACTIVE = 40
    SURFING = 50
    WARMING = 60
    SETUP = 65
    READY = 70
    NEW = 100

    ACCOUNT_STATUS_CHOICES = (
        (NEW, _('New')),
        (ACTIVE, _('Active')),
        (BANNED, _('Banned')),
        (LOGOUT, _('Logged out')),
        (ON_VERIFY, _('On verification')),
        (INACTIVE, _('Inactive')),
        (SURFING, _('Surfing')),
        (WARMING, _('Warming')),
        (SETUP, _('Setup')),
        (READY, _('Ready to use')),
    )

    country_code = models.CharField(default='UA', max_length=2)
    name = models.CharField(_('Account name'), max_length=255, null=True, blank=True)
    login = models.CharField(_('Login'), max_length=255, null=True, blank=True)
    password = models.CharField(_('Password'), max_length=255, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_accounts')
    supplier = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='suppling_accounts', null=True, blank=True
    )  # supplier
    price = models.DecimalField(_('Account price'), max_digits=8, decimal_places=2, default=0)

    mla_profile_id = models.UUIDField(_('Multiloginapp profile ID'), null=True, blank=True)
    mla_profile_data = models.JSONField(
        _('Multiloginapp profile data'), encoder=DjangoJSONEncoder, null=True, blank=True
    )

    manager = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managing_accounts'
    )
    comment = models.CharField(_('Comment'), max_length=256, null=True, blank=True)

    status = FSMIntegerField(_('Account status'), choices=ACCOUNT_STATUS_CHOICES, default=NEW, protected=True)
    status_comment = models.CharField(_('Status Comment'), max_length=1024, null=True, blank=True)
    # Для сортировки на странице списка акков
    status_changed_at = models.DateTimeField(default=timezone.now)

    # FIN data
    card_number = CardNumberField(_('Credit card number'), null=True, blank=True)
    financial_comment = models.CharField(_('Financial Comment'), max_length=1024, null=True, blank=True)

    fb_access_token = models.CharField(_('FB access token'), max_length=512, null=True, blank=True)
    fb_id = models.BigIntegerField(_('FB ID'), null=True, blank=True)

    campaign = models.ForeignKey('Campaign', on_delete=models.PROTECT, null=True, blank=True, related_name='accounts')

    domain = models.CharField(_('Tracker domain'), max_length=255, null=True, blank=True)
    tags = ArrayField(models.CharField(max_length=1024), blank=True, null=True, db_index=True)

    # Proxy data
    proxy_host = models.CharField(max_length=128, null=True, blank=True)
    proxy_port = models.PositiveIntegerField(null=True, blank=True)
    proxy_login = models.CharField(max_length=64, null=True, blank=True)
    proxy_password = models.CharField(max_length=64, null=True, blank=True)

    # Stats data
    fb_spends_today = models.DecimalField(_('Account FB spends today'), max_digits=10, decimal_places=2, default=0)
    fb_spends_yesterday = models.DecimalField(
        _('Account FB spends yesterday'), max_digits=10, decimal_places=2, default=0
    )
    fb_spends = models.DecimalField(_('Account FB spends'), max_digits=10, decimal_places=2, default=0)
    total_spends = models.DecimalField(
        _('Account full spends'), max_digits=10, decimal_places=2, null=True, blank=True
    )

    total_paid = models.DecimalField(_('Total paid'), max_digits=10, decimal_places=2, default=0)

    # Cached TopUPs data
    total_funds = models.DecimalField(_('Account funds'), max_digits=10, decimal_places=2, default=0)
    last_funded = models.DecimalField(_('Account last topup'), max_digits=10, decimal_places=2, default=0)
    funds_wait = models.DecimalField(_('Account funds wait'), max_digits=10, decimal_places=2, default=0)

    # Important dates
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    paid_till = models.DateTimeField(default=default_paid_till)

    phone = models.CharField(validators=[PHONE_REGEX], max_length=17, null=True, blank=True)
    email = models.EmailField(_('Email'), null=True, blank=True)
    email_password = models.CharField(_('Email Password'), max_length=255, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    fieldtracker = FieldTracker()

    def __str__(self):
        return f'Account: {self.country_code} {self.id}'

    class Meta:
        ordering = ('-created_at',)

    @cached_property
    def display_name(self):
        return f'{self.country_code} {self.id}'

    @cached_property
    def age(self):
        end_date = timezone.now()
        if self.status == Account.BANNED:
            log = AccountLog.objects.filter(log_type=AccountLog.STATUS, status=Account.BANNED, account=self).first()
            if log:
                end_date = log.start_at
        return end_date - self.created_at

    @classmethod
    @transaction.atomic
    def create(
        cls,
        user: User,
        login: str,
        password: str,
        price: Decimal,
        country_code='UA',
        comment: str = None,
        supplier: User = None,
        mla_profile_id: str = None,
        fb_access_token: str = None,
        tags: Optional[List[str]] = None,
    ) -> models.Model:
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        account_data = {
            'created_by_id': user.id,
            'supplier_id': supplier.id if supplier else user.id,
            'login': login,
            'password': password,
            'country_code': country_code,
            'comment': comment,
            'mla_profile_id': mla_profile_id,
            'fb_access_token': fb_access_token,
            'created_at': now,
            'price': price,
            # 'paid_till': now,
        }
        if user.role in [User.MEDIABUYER, User.FARMER, User.JUNIOR]:
            account_data['manager_id'] = user.id

        if tags:
            account_data['tags'] = tags
            for tag in tags:
                Tag.objects.get_or_create(name=tag)

        account = cls.objects.create(**account_data)

        Action.create(
            actor=user, action_datetime=now, verb='created account', action_object=account, data=account_data
        )

        AccountLog.log_change(
            account=account, log_type=AccountLog.STATUS, now=now, status=Account.NEW, changed_by=user
        )

        if not account.mla_profile_id:
            from core.tasks.core import create_mla_profile

            shareto_id = supplier.id if supplier is not None else user.id
            # обрабатываем только в конце транзакции
            transaction.on_commit(lambda: create_mla_profile.delay(account_id=account.id, shareto_id=shareto_id))
        return account

    @classmethod
    @transaction.atomic
    def update(cls, pk: int, action_verb: str, **kwargs) -> models.Model:
        now = kwargs.pop('updated_at', timezone.now())  # Для того, чтобы время было одинаковое везде
        # TODO: для забаненых ТОЛЬКО СТАТУС И ТОЛЬКО total_spends
        updated_by = kwargs.pop('updated_by', None)

        account = cls.objects.select_for_update().get(pk=pk)

        if {'card_balance', 'card_number'}.issubset(set(kwargs)) and account.card_number != kwargs['card_number']:
            account.add_cart_balance(updated_by, kwargs.pop('card_balance'))

        if 'total_spends' in kwargs:
            account.set_total_spend(kwargs.pop('total_spends'))

        if 'status' in kwargs:
            # Меняем статус отдельным методом + Пишем лог
            new_status = kwargs.pop('status')
            account.change_status(
                new_status, status_comment=kwargs.pop('status_comment', None), changed_by=updated_by, now=now
            )

        if 'password' in kwargs and kwargs['password'] != account.password:
            # Меняем пасс отдельным методом + Пишем лог
            account.change_password(kwargs.pop('password'), changed_by=updated_by, now=now)

        if 'manager' in kwargs and kwargs['manager'] != account.manager:
            # Меняем менеджера отдельным методом + Пишем лог + Нотификацию
            account.change_manager(kwargs.pop('manager'), changed_by=updated_by, now=now)

        if 'fb_access_token' in kwargs and kwargs['fb_access_token'] != account.fb_access_token:
            account.change_token(kwargs.pop('fb_access_token'), changed_by=updated_by)

        # if 'card_number' in kwargs and kwargs['card_number'] != account.card_number:
        #     account.change_card(kwargs.pop('card_number'), changed_by=updated_by, now=now)

        if 'tags' in kwargs:
            for tag in kwargs['tags']:
                Tag.objects.get_or_create(name=tag)

        if 'supplier' in kwargs and kwargs['supplier'] != account.supplier:
            # Шарим профиль на саплаера
            if account.mla_profile_id and kwargs['supplier'].mla_group_id:

                from core.tasks.core import share_mla_profile

                transaction.on_commit(
                    lambda: share_mla_profile.delay(account_id=account.id, shareto_id=kwargs['supplier'].id)
                )

        for field_name, value in kwargs.items():
            setattr(account, field_name, value)

        changed_data = account.get_changed_data()
        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            account.updated_at = now
            update_fields.append('updated_at')

            account.save(update_fields=update_fields)

            Action.create(
                actor=updated_by, action_datetime=now, verb=action_verb, action_object=account, data=changed_data
            )
        return account

    def set_total_spend(self, total_spends):
        """
        При бане акка вносим окончательный спенд и пересчитываем стату
        """
        self.total_spends = total_spends

        from core.tasks.stats import set_total_spend_stats

        # обрабатываем только в конце транзакции
        transaction.on_commit(lambda: set_total_spend_stats.delay(account_id=self.id))

    @transaction.atomic
    def recalc_spends(self):
        """
        Пересчитывает спенд для отображения в табличке - сегодня, вчера, все время
        """
        yesterday = timezone.now().date() - datetime.timedelta(days=1)
        today = timezone.now().date()

        spends_yesterday = Sum(F('spend'), filter=Q(date=yesterday))
        spends_today = Sum(F('spend'), filter=Q(date=today))

        # TODO: считать по стате юзерской core_useradaccountdaystat
        total_spend = AdAccountDayStat.objects.filter(account=self).aggregate(
            total_spends=Sum('spend'), spends_today=spends_today, spends_yesterday=spends_yesterday
        )
        # Лочим на всякий случай
        account = Account.objects.select_for_update().get(id=self.id)

        account.fb_spends = total_spend.get('total_spends', 0) or 0
        account.fb_spends_today = total_spend.get('spends_today', 0) or 0
        account.fb_spends_yesterday = total_spend.get('spends_yesterday', 0) or 0
        account.save(update_fields=['fb_spends', 'fb_spends_today', 'fb_spends_yesterday'])

    @transaction.atomic
    def add_cart_balance(self, updated_by, card_balance: Decimal, adaccount=None) -> None:
        """
        При добавлении карты с указанием баланса создает заапрувленный Мани реквест с суммой на карте
        """
        request_data = {"amount": str(card_balance), "category": "topup", "account_id": self.id}
        if adaccount:
            request_data['adaccount_id'] = adaccount.id

        user_request = UserRequest.create(
            user=updated_by,
            request_type='money',
            comment='auto on card attach',
            request_data=request_data,
            notify=False,
        )
        user_request.update(
            pk=user_request.id,
            updated_by=updated_by,
            status=UserRequest.APPROVED,
            request_data={"actual_amount": str(card_balance), "status_comment": "auto"},
            notify=False,
        )

    def change_manager(self, manager: User, now: datetime.datetime, changed_by: Optional[User] = None):
        self.manager = manager
        # Сбрасываем кампании
        self.campaign = None
        # Тут в цикле для истории изменений
        adaccounts = self.adaccounts.filter(campaign__isnull=False)
        for adaccount in adaccounts:
            AdAccount.update(
                pk=adaccount.id,
                action_verb='updated on manager change',
                campaign=None,
                updated_by=changed_by,
                updated_at=now,
            )

        AccountLog.log_change(
            account=self, log_type=AccountLog.MANAGER, manager=self.manager, now=now, changed_by=changed_by
        )
        if manager:
            # Если выдали акк менеджеру и у акка статус нью - меняем его на серфинг
            if self.status == Account.NEW:
                self.change_status(new_status=Account.SURFING, now=now, changed_by=changed_by)

            # Шлем уведомление про то, что выдали акк
            data = {
                'message': render_to_string('accounts/change_manager.html', {'account': self}),
                'account_id': self.id,
            }
            Notification.create(
                recipient=manager, level=Notification.INFO, category=Notification.ACCOUNT, data=data, sender=changed_by
            )
            # Шарим профиль на нового юзера
            if self.mla_profile_id and manager.mla_group_id:
                from core.tasks.core import share_mla_profile

                #
                # # Шарим тимлиду
                # if manager.team:
                #     teamlead = User.objects.filter(team=manager.team, role=User.TEAMLEAD).first()
                #     if teamlead and teamlead.mla_group_id:
                #         transaction.on_commit(
                #             lambda: share_mla_profile.delay(account_id=self.id, shareto_id=teamlead.id)
                #         )
                # обрабатываем только в конце транзакции
                transaction.on_commit(
                    lambda: share_mla_profile.delay(
                        account_id=self.id, shareto_id=manager.id, proxy_data=self.get_proxy_data()
                    )
                )

    def get_manager_on_date(self, date: datetime.date) -> User:
        """На случай потери старой статы можно будет примерно посчитать, кому засчитывать траф"""
        log = (
            AccountLog.objects.filter(
                Q(start_at__date__lte=date, end_at__date__gte=date) | Q(start_at__date__lte=date, end_at__isnull=True),
                account=self,
                log_type=AccountLog.MANAGER,
            )
            .order_by('-start_at')
            .first()
        )
        if log:
            return log.manager
        # return None
        return self.manager

    @property
    def has_campaign(self) -> bool:
        has_campaign = cache.get(f'has_campaign_{self.id}')
        if has_campaign is None:
            has_campaign = self.get_active_campaigns().exists()
            cache.set(f'has_campaign_{self.id}', has_campaign, 60 * 5)
        return has_campaign

    def get_active_campaigns(self) -> QuerySet:
        # if self.campaign_id is not None:
        #     return Campaign.objects.filter(id=self.campaign_id)
        # FIXME:
        # if self.adaccounts.exclude(
        #     status__in=[AdAccount.FB_DISABLED, AdAccount.FB_CLOSED, AdAccount.FB_ANY_CLOSED]
        # ).exists():
        campaign_ids = self.adaccounts.exclude(
            status__in=[AdAccount.FB_DISABLED, AdAccount.FB_CLOSED, AdAccount.FB_ANY_CLOSED]
        ).values_list('campaign_id', flat=True)
        if campaign_ids:
            return Campaign.objects.filter(id__in=campaign_ids)

        return Campaign.objects.none()

    def get_all_campaigns(self) -> QuerySet:
        if self.campaign_id is not None:
            return Campaign.objects.filter(id=self.campaign_id)

        # FIXME:
        if self.adaccounts.all().exists():
            campaign_ids = self.adaccounts.all().values_list('campaign_id', flat=True)
            if campaign_ids:
                return Campaign.objects.filter(id__in=campaign_ids)

        return Campaign.objects.none()

    def change_token(self, fb_access_token: str, changed_by: Optional[User] = None):
        # Добавили токен
        if fb_access_token is not None and self.fb_access_token is None:
            # Если добавили токен - надо загрузить данные
            from core.tasks.facebook import load_account_fb_data

            transaction.on_commit(lambda: load_account_fb_data.delay(self.pk))
        # Удалили токен
        elif fb_access_token is None and self.fb_access_token is not None:
            if self.manager:
                data = {
                    'message': render_to_string('accounts/clear_token.html', {'account': self}),
                    'account_id': self.id,
                }
                Notification.create(
                    recipient=self.manager,
                    level=Notification.CRITICAL,
                    category=Notification.ACCOUNT,
                    data=data,
                    sender=changed_by,
                )

        self.fb_access_token = fb_access_token

    def change_password(self, password: str, now: datetime.datetime, changed_by: Optional[User] = None):
        self.password = password

        # При смене пароля саплаером и статусе логаут надо вернуть предыдущий статус и уведомить баера
        if changed_by == self.supplier:
            recipient = self.manager
            if self.status == Account.LOGOUT:
                last_status = self.last_status
                if last_status is not None:
                    self.change_status(last_status, changed_by=changed_by, now=now)
        else:
            # При смене пароля баером или фармером надо создать уведомление саплаеру
            recipient = self.supplier

        if recipient is not None and recipient != changed_by:
            # Шлем сообщение про смену пароля
            data = {
                'message': render_to_string('accounts/change_password.html', {'account': self}),
                'account_id': self.id,
            }
            Notification.create(
                recipient=recipient,
                level=Notification.WARNING,
                category=Notification.ACCOUNT,
                data=data,
                sender=changed_by,
            )

    def change_status(
        self, new_status: int, now: datetime.datetime, status_comment: str = None, changed_by: Optional[User] = None
    ):
        STATUS_METHOD_MAP = {
            Account.NEW: 'new',
            Account.SURFING: 'surfing',
            Account.WARMING: 'warming',
            Account.SETUP: 'setup',
            Account.READY: 'ready',
            Account.ACTIVE: 'active',
            Account.INACTIVE: 'inactive',
            Account.ON_VERIFY: 'on_verify',
            Account.LOGOUT: 'logout',
            Account.BANNED: 'banned',
        }
        if self.status != new_status:
            self.status_changed_at = now
            AccountLog.log_change(
                account=self, log_type=AccountLog.STATUS, status=new_status, now=now, changed_by=changed_by
            )
        status = STATUS_METHOD_MAP[new_status]
        getattr(self, status)(changed_by, status_comment)

        self.status_comment = status_comment

        # Для статусов Серфинг и Ворминг ставим время начала САМОГО первого изменения этого статуса
        # Потом будем сортировать по этой дате
        if new_status in [Account.SURFING, Account.WARMING]:
            account_log = AccountLog.objects.filter(log_type=AccountLog.STATUS, status=new_status, account=self)
            if account_log.exists():
                account_log = account_log.earliest('start_at')
                self.status_changed_at = account_log.start_at

        if self.manager and changed_by != self.manager:
            data = {
                'message': render_to_string('accounts/change_status.html', {'account': self}),
                'account_id': self.id,
            }
            Notification.create(
                recipient=self.manager,
                level=Notification.INFO,
                category=Notification.ACCOUNT,
                data=data,
                sender=changed_by,
            )

        cache.delete(f'last_status_{self.id}')
        cache.delete(f'status_duration_{self.id}')

    @transition(
        field=status,
        source=[SURFING, LOGOUT, BANNED],
        target=NEW,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def new(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        pass

    @transition(
        field=status,
        source=[NEW, LOGOUT, ON_VERIFY, SETUP, INACTIVE, BANNED],
        target=SURFING,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def surfing(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        pass

    @transition(
        field=status,
        source=[SURFING, LOGOUT, ON_VERIFY, SETUP, INACTIVE, BANNED],
        target=WARMING,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def warming(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        pass

    @transition(
        field=status,
        source=[ACTIVE, LOGOUT, ON_VERIFY, INACTIVE, WARMING, READY, BANNED, SETUP],
        target=SETUP,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def setup(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        pass

    @transition(
        field=status,
        source=[ACTIVE, LOGOUT, ON_VERIFY, INACTIVE, WARMING, SETUP, BANNED],
        target=READY,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def ready(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        pass

    @transition(
        field=status,
        source=[LOGOUT, ON_VERIFY, INACTIVE, READY, SETUP, BANNED, WARMING],
        target=ACTIVE,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def active(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        pass

    @transition(
        field=status,
        source=[LOGOUT, ON_VERIFY, ACTIVE, READY, SETUP, BANNED],
        target=INACTIVE,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def inactive(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        pass

    @transition(
        field=status,
        source=[LOGOUT, ACTIVE, INACTIVE, WARMING, READY, SETUP, BANNED, SURFING],
        target=ON_VERIFY,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def on_verify(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        # При верифе надо создать уведомление саплаеру
        recipients = []
        if changed_by != self.manager and self.manager is not None:
            recipients.append(self.manager)

        data = {
            'message': render_to_string('accounts/verify.html', {'account': self, 'reason': status_comment}),
            'account_id': self.id,
            'reason': status_comment,
        }
        for recipient in recipients:
            Notification.create(
                recipient=recipient,
                level=Notification.CRITICAL,
                category=Notification.ACCOUNT,
                data=data,
                sender=changed_by,
            )

    @transition(
        field=status,
        source=[ACTIVE, INACTIVE, SURFING, WARMING, READY, SETUP, NEW, ON_VERIFY, BANNED, LOGOUT],
        target=LOGOUT,
        permission=lambda instance, user: (
            not instance.status == Account.BANNED or user.role in [User.ADMIN, User.MANAGER]
        ),
    )
    def logout(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        # При логауте надо создать уведомление саплаеру
        if changed_by != self.supplier:
            data = {
                'message': render_to_string('accounts/logout.html', {'account': self, 'reason': status_comment}),
                'account_id': self.id,
            }
            Notification.create(
                recipient=self.supplier,
                level=Notification.CRITICAL,
                category=Notification.ACCOUNT,
                data=data,
                sender=changed_by,
            )
            # и если это автоматом, то и баеру
            if changed_by is None and self.manager is not None:
                Notification.create(
                    recipient=self.manager, level=Notification.INFO, category=Notification.ACCOUNT, data=data
                )
        # Очищаем токен
        self.fb_access_token = None

    @transition(
        field=status, source=[LOGOUT, ACTIVE, INACTIVE, SURFING, WARMING, READY, SETUP, NEW, ON_VERIFY], target=BANNED
    )
    def banned(self, changed_by: Optional[User] = None, status_comment: str = None) -> None:
        # При бане надо финансисту для учета статы
        data = {'message': render_to_string('accounts/banned.html', {'account': self}), 'account_id': self.id}
        # + Продублировать саплаеру
        Notification.create(
            recipient=self.supplier,
            level=Notification.WARNING,
            category=Notification.ACCOUNT,
            data=data,
            sender=changed_by,
        )
        recipients = User.get_recipients(roles=[User.FINANCIER])
        for recipient in recipients:
            # noinspection PyTypeChecker
            Notification.create(
                recipient=recipient,
                level=Notification.WARNING,
                category=Notification.ACCOUNT,
                data=data,
                sender=changed_by,
            )

    @property
    def last_status(self) -> Optional[int]:
        last_status = cache.get(f'last_status_{self.id}')
        if last_status:
            if last_status == 'null':
                last_status = None
            return last_status

        last_status = (
            AccountLog.objects.filter(account=self, log_type=AccountLog.STATUS, end_at__isnull=False)
            .order_by('-end_at')
            .first()
        )
        if last_status and last_status.status is not None:
            cache.set(f'last_status_{self.id}', last_status.status, 60 * 60)  # 60 minutes
            return last_status.status
        else:
            cache.set(f'last_status_{self.id}', 'null', 60 * 60)  # 60 minutes
        return None

    def get_available_statuses(self, user) -> List[int]:
        return [x.target for x in self.get_available_user_status_transitions(user) if x.target != self.READY]

    @property
    def status_duration(self) -> datetime.timedelta:
        duration = cache.get(f'status_duration_{self.id}')
        if duration:
            return datetime.timedelta(seconds=duration)

        end_at = Case(
            When(end_at__isnull=True, then=timezone.now()), default=F('end_at'), output_field=DateTimeField()
        )

        duration_expression = ExpressionWrapper(end_at - F('start_at'), output_field=DurationField())
        log_qs = AccountLog.objects.filter(account=self, log_type=AccountLog.STATUS, status=self.status)
        duration = datetime.timedelta(seconds=0)
        if self.status in [Account.SURFING, Account.WARMING]:
            log = log_qs.annotate(duration=duration_expression).aggregate(total_duration=Sum('duration'))
            if log.get('total_duration'):
                duration = log['total_duration']
        else:
            log = (
                log_qs.filter(end_at__isnull=True).order_by('-start_at').annotate(duration=duration_expression).first()
            )
            if log:
                duration = log.duration
        cache.set(f'status_duration_{self.id}', duration.total_seconds(), 60 * 5)  # 5 minutes
        return duration

    def get_proxy_data(self) -> Optional[Dict[str, Any]]:
        if self.proxy_host is not None and self.proxy_port is not None:
            # data = {'host': '64.227.71.32', 'port': 3128}
            data = {'host': self.proxy_host, 'port': self.proxy_port}
            if self.proxy_login and self.proxy_password:
                data['login'] = self.proxy_login
                data['password'] = self.proxy_password
            return data
        elif self.manager is not None and self.manager.proxy_host is not None and self.manager.proxy_port is not None:
            # data = {'host': '64.227.71.32', 'port': 3128}
            data = {'host': self.manager.proxy_host, 'port': self.manager.proxy_port}
            if self.manager.proxy_login and self.manager.proxy_password:
                data['login'] = self.manager.proxy_login
                data['password'] = self.manager.proxy_password
            return data
        return {}

    @property
    def proxy_config(self) -> Optional[Dict[str, Any]]:
        proxy_data = self.get_proxy_data()
        if proxy_data:
            if proxy_data.get('login') and proxy_data.get('password'):
                return {
                    'https': f'http://{proxy_data["login"]}:{proxy_data["password"]}'
                    f'@{proxy_data["host"]}:{proxy_data["port"]}'
                }
            return {'https': f'http://{proxy_data["host"]}:{proxy_data["port"]}'}
        return None


class AccountActivityLog(LogChangedMixin):
    uuid = models.UUIDField('Session UUID', default=uuid.uuid4, db_index=True, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, db_index=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)

    @property
    def duration(self):
        return self.end_at - self.start_at


class AccountLog(models.Model):
    """
    Модель для хранения времени в каждом статусе для подсчета статы по статусам
    + возврата статуса при некоторых действиях с акком + Лог менеджеров акка
    """

    STATUS = 0
    MANAGER = 1
    CARD = 2
    LOG_TYPE_CHOICES = ((STATUS, 'Status'), (MANAGER, 'Manager'), (CARD, 'Card'))
    account = models.ForeignKey(Account, on_delete=models.PROTECT, db_index=True)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)
    log_type = models.PositiveSmallIntegerField(choices=LOG_TYPE_CHOICES, default=STATUS, db_index=True)
    status = models.PositiveIntegerField(choices=Account.ACCOUNT_STATUS_CHOICES, null=True, blank=True, db_index=True)
    manager = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    card_number = CardNumberField(_('Credit card number'), null=True, blank=True, db_index=True)
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='account_logs')

    def __str__(self):
        return f'{self.get_log_type_display()} Log({self.id})'

    class Meta:
        index_together = (('start_at', 'end_at'), ('account', 'status', 'log_type', 'end_at'))

    @classmethod
    def log_change(cls, account, now, log_type, **kwargs):
        try:
            log = cls.objects.select_for_update().get(account=account, log_type=log_type, end_at__isnull=True)
            log.end_at = now
            update_fields = ['end_at']
            # if 'changed_by' in kwargs:
            #     log.changed_by = kwargs['changed_by']
            #     update_fields.append('changed_by')
            log.save(update_fields=update_fields)
        except AccountLog.DoesNotExist:
            pass

        log_data = {
            'account': account,
            'start_at': now,
            'log_type': log_type,
        }
        for key, value in kwargs.items():
            log_data[key] = value
        cls.objects.create(**log_data)


class Campaign(LogChangedMixin):
    campaign_id = models.PositiveIntegerField(db_index=True, unique=True)
    symbol = models.CharField(max_length=16, db_index=True, unique=True)
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    country_code = models.CharField(max_length=2)
    status = models.CharField(max_length=32, default='archived')
    tracking_url = models.CharField(max_length=1024, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    fieldtracker = FieldTracker()

    def __str__(self):
        return f'Campaign: {self.name}'

    def get_account(self):
        adaccount = self.adaccounts.all().first()
        if adaccount:
            return adaccount.account
        else:
            account = self.accounts.all().first()
            if account:
                return account
        return None

    @classmethod
    @transaction.atomic
    def create(
        cls,
        campaign_id: int,
        name: str,
        status: str,
        symbol: str,
        tracking_url: str,
        manager: User = None,
        created_by: User = None,
    ):
        now = timezone.now()
        country_code = name.split('-')[1].strip()[:2]
        campaign_data = {
            'campaign_id': campaign_id,
            'name': name,
            'symbol': symbol,
            'status': status,
            'tracking_url': tracking_url,
            'country_code': country_code,
        }
        if manager:
            campaign_data['user_id'] = manager.id

        campaign = cls.objects.create(**campaign_data)
        Action.create(
            actor=created_by, action_datetime=now, verb='created campaign', action_object=campaign, data=campaign_data
        )

        CampaignLog.log_change(
            campaign=campaign, log_type=CampaignLog.STATUS, now=now, status=campaign.status, changed_by=created_by
        )

        CampaignLog.log_change(
            campaign=campaign,
            log_type=CampaignLog.MANAGER,
            now=now,
            manager_id=campaign.user_id,
            changed_by=created_by,
        )

        return campaign

    @classmethod
    @transaction.atomic
    def update(cls, pk, action_verb, **kwargs):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде

        updated_by = kwargs.pop('updated_by', None)
        campaign = cls.objects.select_for_update().get(pk=pk)

        if 'name' in kwargs:
            campaign.country_code = kwargs['name'].split('-')[1].strip()[:2]

        if 'manager' in kwargs and campaign.user != kwargs['manager']:
            # Пишем лог
            campaign.change_manager(manager=kwargs.pop('manager'), now=now, changed_by=updated_by)

        for field_name, value in kwargs.items():
            setattr(campaign, field_name, value)

        changed_data = campaign.get_changed_data()

        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            campaign.save(update_fields=update_fields)

            Action.create(action_datetime=now, verb=action_verb, action_object=campaign, data=changed_data)
        return campaign

    def change_manager(self, manager: User, now: datetime.datetime, changed_by: Optional[User] = None):
        self.user = manager
        CampaignLog.log_change(
            campaign=self, log_type=CampaignLog.MANAGER, manager_id=manager.id, now=now, changed_by=changed_by
        )

    def get_manager_on_date(self, date):
        """На случай потери старой статы можно будет примерно посчитать, кому засчитывать траф"""
        log = (
            CampaignLog.objects.filter(
                Q(start_at__date__lte=date, end_at__date__gte=date) | Q(start_at__date__lte=date, end_at__isnull=True),
                campaign=self,
                log_type=CampaignLog.MANAGER,
            )
            .order_by('-start_at')
            .first()
        )
        if log:
            return log.manager
        # return None
        return self.user


class CampaignLog(models.Model):
    """
       Модель для хранения времени в каждом статусе для подсчета статы по статусам
       + возврата статуса при некоторых действиях с акком + Лог менеджеров кампании
       """

    STATUS = 0
    MANAGER = 1
    LOG_TYPE_CHOICES = ((STATUS, 'Status'), (MANAGER, 'Manager'))
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, db_index=True)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)
    log_type = models.PositiveSmallIntegerField(choices=LOG_TYPE_CHOICES, default=STATUS, db_index=True)
    status = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    manager = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='campaign_logs')

    class Meta:
        index_together = (('start_at', 'end_at'), ('campaign', 'status', 'log_type', 'end_at'))

    @classmethod
    def log_change(cls, campaign, now, log_type, **kwargs):
        try:
            log = cls.objects.select_for_update().get(campaign=campaign, log_type=log_type, end_at__isnull=True)
            log.end_at = now
            update_fields = ['end_at']
            log.save(update_fields=update_fields)

        except CampaignLog.DoesNotExist:
            pass

        if log_type == cls.STATUS:
            cls.objects.create(
                campaign=campaign,
                start_at=now,
                log_type=log_type,
                status=kwargs['status'],
                changed_by=kwargs.get('changed_by'),
            )
        elif log_type == cls.MANAGER:
            cls.objects.create(
                campaign=campaign,
                start_at=now,
                log_type=log_type,
                manager_id=kwargs['manager_id'],
                changed_by=kwargs.get('changed_by'),
            )


class AccountPayment(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    date = models.DateField()
    amount = models.DecimalField(_('USD Amount'), max_digits=10, decimal_places=2)
    amount_uah = models.DecimalField(_('UAH Amount'), max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FBPage(LogChangedMixin):
    """
    Модель для хранения токенов от страниц для скрытия комментов
    """

    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    page_id = models.BigIntegerField(_('FB page id'))
    name = models.CharField(_('Page name'), max_length=512)
    access_token = models.CharField(_('Page access token'), max_length=255)
    is_published = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(_('Deleted at'), default=None, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    fieldtracker = FieldTracker()

    class Meta:
        unique_together = ('account', 'page_id')

    def __str__(self):
        return self.name

    @classmethod
    @transaction.atomic
    def create(
        cls,
        account: Account,
        page_id: int,
        name: str,
        access_token: str,
        is_published: bool,
        deleted_at: datetime.datetime = None,
    ) -> models.Model:
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        page_data = {
            'account_id': account.id,
            'page_id': page_id,
            'name': name,
            'access_token': access_token,
            'is_published': is_published,
            'deleted_at': deleted_at,
        }
        page = cls.objects.create(**page_data)
        Action.create(
            action_datetime=now, verb='created FB page', action_object=page, target_object=account, data=page_data,
        )
        return page

    @classmethod
    @transaction.atomic
    def update(cls, pk, action_verb='Page updated', **kwargs):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде

        page = cls.objects.select_for_update().get(pk=pk)

        if 'is_published' in kwargs and page.is_published != kwargs['is_published']:
            if kwargs['is_published'] is False:
                page.unpublished()

        for field_name, value in kwargs.items():
            setattr(page, field_name, value)

        changed_data = page.get_changed_data()

        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            page.save(update_fields=update_fields)
            Action.create(action_datetime=now, verb=action_verb, action_object=page, data=changed_data)
        return page

    def unpublished(self):
        if self.account.manager:
            # Шлем уведомление про то, что страницу сняли с публикации
            data = {
                'message': render_to_string('accounts/page_unpublished.html', {'page': self}),
                'account_id': self.id,
            }
            Notification.create(
                recipient=self.account.manager, level=Notification.WARNING, category=Notification.PAGE, data=data
            )


class BusinessManager(LogChangedMixin):
    business_id = models.BigIntegerField(_('BM id'), unique=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='businesses')
    manager = models.ForeignKey(User, on_delete=models.PROTECT, related_name='businesses', null=True, blank=True)
    name = models.CharField(_('BM name'), max_length=256)
    created_at = models.DateTimeField(_('Created at'), default=timezone.now)
    deleted_at = models.DateTimeField(_('Deleted at'), default=None, null=True, blank=True)
    can_create_ad_account = models.BooleanField(_('Can create ad account'), default=False)

    # banned = models.BooleanField(_('Banned'), default=False)
    fieldtracker = FieldTracker()

    def __str__(self):
        return self.name

    def create_share_url(self):
        faker = Faker()
        FacebookAdsApi.init(
            access_token=self.account.fb_access_token, proxies=self.account.proxy_config, api_version='v8.0'
        )
        bm = Business(fbid=self.business_id)
        pending_user = bm.create_business_user(
            fields=['email', 'invite_link', 'status', 'role', 'created_time', 'expiration_time'],
            params={'email': faker.email(), 'role': 'ADMIN'},
        )
        share_url, _ = BusinessShareUrl.objects.update_or_create(
            business=self,
            share_id=pending_user['id'],
            defaults={
                'url': pending_user['invite_link'],
                'email': pending_user['email'],
                'status': pending_user['status'],
                'role': pending_user['role'],
                'created_at': pending_user['created_time'],
                'expire_at': pending_user['expiration_time'],
            },
        )
        return share_url

    @classmethod
    @transaction.atomic
    def create(
        cls,
        business_id: int,
        account: Account,
        name: str,
        created_at: datetime.datetime,
        deleted_at: datetime.datetime = None,
        can_create_ad_account: bool = False,
        manager: User = None,
    ) -> models.Model:
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        business_data = {
            'business_id': business_id,
            'account_id': account.id,
            'manager_id': manager.id if manager else None,
            'name': name,
            'created_at': created_at,
            'deleted_at': deleted_at,
            'can_create_ad_account': can_create_ad_account,
        }
        business = cls.objects.create(**business_data)
        Action.create(
            action_datetime=now,
            verb='created Business Manager',
            action_object=business,
            target_object=account,
            data=business_data,
        )

        BusinessManagerLog.log_change(
            business=business, log_type=BusinessManagerLog.ACCOUNT, now=now, account=business.account
        )
        BusinessManagerLog.log_change(
            business=business, log_type=BusinessManagerLog.MANAGER, now=now, manager=business.manager
        )
        return business

    @classmethod
    @transaction.atomic
    def update(cls, pk, action_verb='updated Business Manager', **kwargs):
        now = kwargs.pop('updated_at', timezone.now())  # Для того, чтобы время было одинаковое везде
        updated_by = kwargs.pop('updated_by') if 'updated_by' in kwargs else None

        business = cls.objects.select_for_update().get(pk=pk)

        if 'manager' in kwargs and kwargs['manager'] != business.manager:
            business.manager = kwargs.pop('manager')
            # Меняем менеджера отдельным методом + Пишем лог + Нотификацию
            BusinessManagerLog.log_change(
                business=business,
                log_type=BusinessManagerLog.MANAGER,
                manager_id=business.manager.id,
                now=now,
                changed_by=updated_by,
            )

        business.deleted_at = None
        for field_name, value in kwargs.items():
            setattr(business, field_name, value)

        changed_data = business.get_changed_data()

        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            business.save(update_fields=update_fields)
            if 'account' in update_fields:
                BusinessManagerLog.log_change(
                    business=business, log_type=BusinessManagerLog.ACCOUNT, now=now, account=business.account
                )
            Action.create(action_datetime=now, verb=action_verb, action_object=business, data=changed_data)

        return business


class BusinessManagerLog(models.Model):
    # STATUS = 0
    MANAGER = 1
    ACCOUNT = 2
    LOG_TYPE_CHOICES = (
        # (STATUS, 'Status'),
        (MANAGER, 'Manager'),
        (ACCOUNT, 'Account'),
    )
    business = models.ForeignKey(BusinessManager, on_delete=models.CASCADE, db_index=True)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)
    log_type = models.PositiveSmallIntegerField(choices=LOG_TYPE_CHOICES, default=ACCOUNT, db_index=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, blank=True, null=True, db_index=True)
    manager = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='bm_logs')

    def __str__(self):
        return f'{self.get_log_type_display()} Log({self.id})'

    class Meta:
        index_together = ('start_at', 'end_at')

    @classmethod
    def log_change(cls, business, now, log_type=ACCOUNT, **kwargs):
        try:
            log = cls.objects.select_for_update().get(business=business, log_type=log_type, end_at__isnull=True)
            log.end_at = now
            update_fields = ['end_at']
            log.save(update_fields=update_fields)
        except BusinessManagerLog.DoesNotExist:
            pass

        log_data = {
            'business': business,
            'start_at': now,
            'log_type': log_type,
        }
        for key, value in kwargs.items():
            log_data[key] = value
        cls.objects.create(**log_data)


class BusinessShareUrl(models.Model):
    business = models.ForeignKey(BusinessManager, on_delete=models.CASCADE, related_name='share_urls')
    share_id = models.BigIntegerField(_('Share url id'), unique=True)
    url = models.URLField(_('Share URL'), max_length=512)
    email = models.EmailField(_('Email'), max_length=512)
    status = models.CharField(_('Status'), max_length=16)
    role = models.CharField(_('Role'), max_length=16)
    created_at = models.DateTimeField(_('Created at'), default=timezone.now)
    expire_at = models.DateTimeField(_('Expiration data'), default=timezone.now)

    class Meta:
        ordering = ('-created_at',)


class AdAccount(LogChangedMixin):
    """
    https://graph.facebook.com/v5.0/me/adaccounts/?fields=account_id,balance,name,age
    &access_token=EAABsbCS1iHgBAAZC2T3zYKsawp3LhWwQhW3ESIEMCDpwiRluFLPPZAB7r9B8iMdEtvd9
    PCX3p2zVZChOaFgtNtZAFAIkv1ccveZCP4duzZAJ2m04ADNKiglZCtoAYnUaU1UPFwcIjsv6HDZBskWNxn0NPZBilKIThU7ZB2bayyFmfArgZDZD

    Status
    1 = ACTIVE
    2 = DISABLED
    3 = UNSETTLED
    7 = PENDING_RISK_REVIEW
    8 = PENDING_SETTLEMENT
    9 = IN_GRACE_PERIOD
    100 = PENDING_CLOSURE
    101 = CLOSED
    201 = ANY_ACTIVE
    202 = ANY_CLOSED

    Disable reason
    0 = NONE
    1 = ADS_INTEGRITY_POLICY
    2 = ADS_IP_REVIEW
    3 = RISK_PAYMENT
    4 = GRAY_ACCOUNT_SHUT_DOWN
    5 = ADS_AFC_REVIEW
    6 = BUSINESS_INTEGRITY_RAR
    7 = PERMANENT_CLOSE
    8 = UNUSED_RESELLER_ACCOUNT
    9 = UNUSED_ACCOUNT
    """

    # ADACCOUNT STATUS
    FB_ACTIVE = 1
    FB_DISABLED = 2
    FB_UNSETTLED = 3
    FB_PENDING_RISK_REVIEW = 7
    FB_PENDING_SETTLEMENT = 8
    FB_IN_GRACE_PERIOD = 9
    FB_PENDING_CLOSURE = 100
    FB_CLOSED = 101
    FB_ANY_ACTIVE = 201
    FB_ANY_CLOSED = 202

    # ADACCOUNT DISABLE REASON
    FB_NONE = 0
    FB_ADS_INTEGRITY_POLICY = 1
    FB_ADS_IP_REVIEW = 2
    FB_RISK_PAYMENT = 3
    FB_GRAY_ACCOUNT_SHUT_DOWN = 4
    FB_ADS_AFC_REVIEW = 5
    FB_BUSINESS_INTEGRITY_RAR = 6
    FB_PERMANENT_CLOSE = 7
    FB_UNUSED_RESELLER_ACCOUNT = 8
    FB_UNUSED_ACCOUNT = 9

    ADACCOUNT_STATUS_CHOICES = (
        (FB_ACTIVE, 'Active'),
        (FB_DISABLED, 'Disabled'),
        (FB_UNSETTLED, 'Unsettled'),
        (FB_PENDING_RISK_REVIEW, 'Pending risk review'),
        (FB_PENDING_SETTLEMENT, 'Pending settlement'),
        (FB_IN_GRACE_PERIOD, 'In grace period'),
        (FB_PENDING_CLOSURE, 'Pending closure'),
        (FB_CLOSED, 'Closed'),
        (FB_ANY_ACTIVE, 'Any active'),
        (FB_ANY_CLOSED, 'Any closed'),
    )

    ADACCOUNT_DISABLE_REASON_CHOICES = (
        (FB_NONE, None),
        (FB_ADS_INTEGRITY_POLICY, 'Ads integrity policy'),
        (FB_ADS_IP_REVIEW, 'Ads ip review'),
        (FB_RISK_PAYMENT, 'Risk payment'),
        (FB_GRAY_ACCOUNT_SHUT_DOWN, 'Gray account shut down'),
        (FB_ADS_AFC_REVIEW, 'Ads afc review'),
        (FB_BUSINESS_INTEGRITY_RAR, 'Business integrity rar'),
        (FB_PERMANENT_CLOSE, 'Permanent close'),
        (FB_UNUSED_RESELLER_ACCOUNT, 'Unused reseller account'),
        (FB_UNUSED_ACCOUNT, 'Unused account'),
    )
    business = models.ForeignKey(
        BusinessManager, on_delete=models.SET_NULL, null=True, blank=True, related_name='adaccounts'
    )
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='adaccounts')
    manager = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(_('Fb adaccount name'), max_length=256)
    adaccount_id = models.BigIntegerField(_('Fb adaccount id'))
    status = models.PositiveSmallIntegerField(
        _('Ad account status'), default=FB_ACTIVE, choices=ADACCOUNT_STATUS_CHOICES
    )
    disable_reason = models.PositiveSmallIntegerField(
        _('Ad account disable reason'),
        default=FB_NONE,
        choices=ADACCOUNT_DISABLE_REASON_CHOICES,
        null=True,
        blank=True,
    )
    amount_spent = models.DecimalField(_('Amount spends'), max_digits=10, decimal_places=2, default=0)
    balance = models.DecimalField(_('Balance'), max_digits=10, decimal_places=2, default=0)
    limit = models.DecimalField(_('Day spends limit'), max_digits=10, decimal_places=2, null=True, blank=True)
    payment_cycle = models.DecimalField(_('Payment cycle'), max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(_('Currency'), max_length=3, null=True, blank=True)
    timezone_name = models.CharField(_('Timezone name'), max_length=32, null=True, blank=True)
    timezone_offset_hours_utc = models.IntegerField(null=True, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, null=True, blank=True, related_name='adaccounts')
    pixels = models.JSONField(null=True, blank=True)
    cards = models.ManyToManyField('Card', through='AdAccountCreditCard')

    bills_load_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True)

    fieldtracker = FieldTracker()

    class Meta:
        unique_together = ('account', 'adaccount_id')

    def __str__(self):
        return f'{self.adaccount_id}: {self.name}'

    @classmethod
    @transaction.atomic
    def create(
        cls,
        adaccount_id: int,
        account: Account,
        name: str,
        status: int,
        balance: Decimal,
        amount_spent: Decimal,
        limit: Decimal,
        created_at: datetime.datetime,
        currency: str,
        timezone_name: str,
        timezone_offset_hours_utc: int,
        payment_cycle: Decimal = None,
        business_id: int = None,
        pixels: Dict[str, Any] = None,
        disable_reason: int = None,
        manager: User = None,
    ) -> models.Model:
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        adaccount_data = {
            'account_id': account.id,
            'manager_id': manager.id if manager else None,
            'adaccount_id': adaccount_id,
            'business_id': business_id,
            'name': name,
            'status': status,
            'disable_reason': disable_reason,
            'balance': balance,
            'amount_spent': amount_spent,
            'payment_cycle': payment_cycle,
            'limit': limit,
            'created_at': created_at,
            'pixels': pixels,
            'currency': currency,
            'timezone_name': timezone_name,
            'timezone_offset_hours_utc': timezone_offset_hours_utc,
        }
        adaccount = cls.objects.create(**adaccount_data)
        Action.create(
            action_datetime=now,
            verb='created adaccount',
            action_object=adaccount,
            target_object=account,
            data=adaccount_data,
        )
        AdAccountLog.log_change(adaccount=adaccount, log_type=AdAccountLog.STATUS, now=now, status=adaccount.status)
        AdAccountLog.log_change(adaccount=adaccount, log_type=AdAccountLog.MANAGER, now=now, manager=adaccount.manager)
        return adaccount

    @classmethod
    @transaction.atomic
    def update(cls, pk: int, action_verb: str, **kwargs):
        now = kwargs.pop('updated_at', timezone.now())  # Для того, чтобы время было одинаковое везде
        updated_by = kwargs.pop('updated_by') if 'updated_by' in kwargs else None

        adaccount = cls.objects.select_for_update().get(pk=pk)

        if 'manager' in kwargs and kwargs['manager'] != adaccount.manager:
            adaccount.manager = kwargs.pop('manager')
            # Меняем менеджера отдельным методом + Пишем лог + Нотификацию
            AdAccountLog.log_change(
                adaccount=adaccount,
                log_type=AdAccountLog.MANAGER,
                manager_id=adaccount.manager.id,
                now=now,
                changed_by=updated_by,
            )

        if 'campaign' in kwargs:
            cache.delete(f'has_campaign_{adaccount.account_id}')
        # Сбрасываем алерты после списания
        if 'balance' in kwargs:
            if adaccount.balance > kwargs['balance']:
                redis.srem('sent_billing_alert', adaccount.adaccount_id)
                redis.srem('sent_overbilling_alert', adaccount.adaccount_id)

        if 'status' in kwargs and adaccount.status != kwargs['status']:
            # Пишем лог + нотификация
            adaccount.change_status(
                kwargs.pop('status'), disable_reason=kwargs.pop('disable_reason', None), changed_by=updated_by, now=now
            )

        for field_name, value in kwargs.items():
            setattr(adaccount, field_name, value)

        changed_data = adaccount.get_changed_data()
        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            # Если только баланс и спенд, то не надо лог записывать
            short_fields = [x for x in update_fields if x not in ['balance', 'amount_spent']]
            if len(short_fields) > 1:
                Action.create(
                    action_datetime=now,
                    verb=action_verb,
                    action_object=adaccount,
                    target_object=adaccount.account,
                    data=changed_data,
                )

            adaccount.updated_at = now
            update_fields.append('updated_at')
            adaccount.save(update_fields=update_fields)

            adaccount.check_threshold()

        return adaccount

    def change_status(
        self, new_status: int, now: datetime.datetime, changed_by: Optional[User] = None, disable_reason: int = None
    ) -> None:
        self.status = new_status
        self.disable_reason = disable_reason
        # надо для учета статы + записать в статистику
        AdAccountLog.log_change(adaccount=self, log_type=AdAccountLog.STATUS, status=new_status, now=now)

        if self.account.manager:
            message = render_to_string('adaccounts/change_status.html', {'adaccount': self})
            data = {'message': message, 'account_id': self.account_id, 'adaccount_id': self.id}
            Notification.create(
                recipient=self.account.manager,
                level=Notification.CRITICAL,
                category=Notification.ADACCOUNT,
                data=data,
                sender=changed_by,
            )

    def check_threshold(self) -> None:
        min_threshold = Decimal(Config.get_value('min_threshold'))
        threshold_limit = Decimal(Config.get_value('threshold_limit'))
        if self.account.manager and self.payment_cycle:
            if self.payment_cycle >= min_threshold and self.balance >= self.payment_cycle * threshold_limit:
                if not redis.sismember('sent_billing_alert', self.adaccount_id):
                    message = render_to_string('adaccounts/billing_alert.html', {'adaccount': self})
                    data = {'message': message, 'account_id': self.account_id, 'adaccount_id': self.adaccount_id}
                    Notification.create(
                        recipient=self.account.manager,
                        level=Notification.INFO,
                        category=Notification.ADACCOUNT,
                        data=data,
                    )
                    redis.sadd('sent_billing_alert', self.adaccount_id)

            elif self.balance >= self.payment_cycle:
                if not redis.sismember('sent_overbilling_alert', self.adaccount_id):
                    message = render_to_string('adaccounts/overbilling_alert.html', {'adaccount': self})
                    data = {'message': message, 'account_id': self.account_id, 'adaccount_id': self.adaccount_id}
                    Notification.create(
                        recipient=self.account.manager,
                        level=Notification.WARNING,
                        category=Notification.ADACCOUNT,
                        data=data,
                    )
                    redis.sadd('sent_overbilling_alert', self.adaccount_id)

    def get_manager_on_date(self, date: datetime.date) -> User:
        """На случай потери старой статы можно будет примерно посчитать, кому засчитывать траф"""
        log = (
            AdAccountLog.objects.filter(
                Q(start_at__date__lte=date, end_at__date__gte=date) | Q(start_at__date__lte=date, end_at__isnull=True),
                adaccount=self,
                log_type=AdAccountLog.MANAGER,
            )
            .order_by('-start_at')
            .first()
        )
        if log:
            return log.manager
        # return None
        return self.manager

    @property
    def cards_balance(self):
        cards = AdAccountCreditCard.objects.filter(adaccount=self).values_list('card_id', flat=True)
        cards_ids = list(cards)
        finances = Card.objects.filter(id__in=cards_ids, number__isnull=False).aggregate(
            total_funds=Sum('funds'), total_spends=Sum('fb_spends')
        )
        funds = finances.get('total_funds') or Decimal('0.00')
        spends = finances.get('total_spends') or Decimal('0.00')
        return funds - spends

    @property
    def billed_to(self):
        last_transaction = self.adaccounttransaction_set.all().order_by('-end_at_ts').first()
        if last_transaction:
            return last_transaction.end_at_ts
        return None


class AdAccountCreditCard(LogChangedMixin):
    adaccount = models.ForeignKey('AdAccount', on_delete=models.CASCADE)
    card = models.ForeignKey('Card', on_delete=models.SET_NULL, null=True, blank=True)
    credential_id = models.BigIntegerField(_('FB ID'), null=True, blank=True)
    display_string = models.CharField(max_length=24, null=True, blank=True)

    funds = models.DecimalField(_('Total TopUps'), max_digits=10, decimal_places=2, default=0)
    fb_spends = models.DecimalField(_('Spends by FB Transactions'), max_digits=10, decimal_places=2, default=0)
    spend = models.DecimalField(_('Full spend'), max_digits=10, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    fieldtracker = FieldTracker()

    def __str__(self):
        return self.display_string or str(self.id)

    @transaction.atomic
    def recalc_spends(self):
        queryset = AdAccountTransaction.objects.filter(adaccount_card=self, status='completed')

        refunds = queryset.filter(adaccount_card=self, charge_type='refund')
        spends = queryset.filter(adaccount_card=self, charge_type='payment')

        funds = queryset.filter(adaccount_card=self, charge_type='topup')
        withdraw = queryset.filter(adaccount_card=self, charge_type='withdraw')

        total_refunds = refunds.aggregate(amount=Sum('amount'))
        total_refunds = total_refunds.get('amount') or Decimal('0.00')

        total_spends = spends.aggregate(amount=Sum('amount'))
        total_spends = total_spends.get('amount') or Decimal('0.00')

        total_funds = funds.aggregate(amount=Sum('amount'))
        total_funds = total_funds.get('amount') or Decimal('0.00')

        total_withdraw = withdraw.aggregate(amount=Sum('amount'))
        total_withdraw = total_withdraw.get('amount') or Decimal('0.00')

        fb_spends = total_spends - total_refunds
        funds = total_funds - total_withdraw

        adaccount_card = AdAccountCreditCard.objects.select_for_update().get(id=self.id)
        adaccount_card.fb_spends = fb_spends
        adaccount_card.funds = funds
        adaccount_card.save(update_fields=['fb_spends', 'funds'])

    @classmethod
    @transaction.atomic
    def create(
        cls, adaccount: AdAccount, display_string: str, credential_id: int, created_at: datetime.datetime = None,
    ):
        if created_at is None:
            created_at = timezone.now()

        credit_card_data = {
            'adaccount_id': adaccount.id,
            'display_string': display_string,
            'credential_id': credential_id,
            'created_at': created_at,
        }
        adaccount_card = cls.objects.filter(credential_id=credential_id, card__isnull=False).first()
        if adaccount_card is not None:
            credit_card_data['card_id'] = adaccount_card.card_id

        credit_card = cls.objects.create(**credit_card_data)
        account = Account.objects.select_for_update().get(pk=adaccount.account_id)
        if account.status == Account.SURFING:
            Account.update(
                pk=account.id, action_verb='Auto update status on credit card create', status=Account.WARMING
            )

        Action.create(
            action_datetime=timezone.now(),
            actor=None,
            verb='AdAccount credit card created',
            action_object=credit_card,
            target_object=adaccount,
            data=credit_card_data,
        )
        return credit_card

    @classmethod
    @transaction.atomic
    def update(cls, pk, updated_by=None, updated_at=None, **kwargs):
        now = updated_at or timezone.now()
        adaccount_card = cls.objects.select_for_update().get(pk=pk)

        for field_name, value in kwargs.items():
            setattr(adaccount_card, field_name, value)

        changed_data = adaccount_card.get_changed_data()
        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            Action.create(
                action_datetime=now,
                actor=updated_by,
                verb='AdAccount Credit card updated',
                action_object=adaccount_card,
                data=changed_data,
            )
            adaccount_card.save(update_fields=update_fields)

        return adaccount_card

    @transaction.atomic
    def create_transaction(self, amount, charge_type, now, reason, card=None, created_by=None):
        # TODO: Action log
        AdAccountTransaction.objects.create(
            adaccount_card=self,
            card=card,
            adaccount=self.adaccount,
            created_by=created_by,
            currency='USD',
            charge_type=charge_type,
            payment_option='credit_card',
            status='completed',
            amount=amount,
            billed_at=now,
            reason=reason,
        )


class Card(LogChangedMixin):
    CC_TYPE_GENERIC = 0
    CC_TYPE_VISA = 1
    CC_TYPE_AMEX = 2
    CC_TYPE_DINERS = 3
    CC_TYPE_DISCOVER = 4
    CC_TYPE_MASTERCARD = 5
    CC_TYPE_ELO = 6
    CC_TYPE_JCB = 7
    CC_TYPE_MIR = 8
    CC_TYPE_UNIONPAY = 9

    CC_TYPES_DICT = {
        'American Express': CC_TYPE_AMEX,
        'Diners Club': CC_TYPE_DINERS,
        'Discover Card': CC_TYPE_DISCOVER,
        'Elo': CC_TYPE_ELO,
        'JCB': CC_TYPE_JCB,
        'MasterCard': CC_TYPE_MASTERCARD,
        'MIR': CC_TYPE_MIR,
        'UnionPay': CC_TYPE_UNIONPAY,
        'Generic': CC_TYPE_GENERIC,
    }

    display_string = models.CharField(max_length=24, db_index=True)
    card_type = models.PositiveSmallIntegerField(choices=CC_TYPE_CHOICES)

    number = CardNumberField(_('Credit card number'), db_index=True)
    comment = models.CharField(_('Financial Comment'), max_length=1024, null=True, blank=True, db_index=True)

    funds = models.DecimalField(_('Total TopUps'), max_digits=10, decimal_places=2, default=0)
    fb_spends = models.DecimalField(_('Spends by FB Transactions'), max_digits=10, decimal_places=2, default=0)
    spend = models.DecimalField(_('Full spend'), max_digits=10, decimal_places=2, null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    fieldtracker = FieldTracker()

    def __str__(self):
        return self.display_string

    class Meta:
        ordering = ('-id',)

    @transaction.atomic
    def recalc_spends(self):
        queryset = AdAccountTransaction.objects.filter(card=self, status='completed')

        refunds = queryset.filter(card=self, charge_type='refund')
        spends = queryset.filter(card=self, charge_type='payment')

        funds = queryset.filter(card=self, charge_type='topup')
        withdraw = queryset.filter(card=self, charge_type='withdraw')

        total_refunds = refunds.aggregate(amount=Sum('amount'))
        total_refunds = total_refunds.get('amount') or Decimal('0.00')

        total_spends = spends.aggregate(amount=Sum('amount'))
        total_spends = total_spends.get('amount') or Decimal('0.00')

        total_funds = funds.aggregate(amount=Sum('amount'))
        total_funds = total_funds.get('amount') or Decimal('0.00')

        total_withdraw = withdraw.aggregate(amount=Sum('amount'))
        total_withdraw = total_withdraw.get('amount') or Decimal('0.00')

        fb_spends = total_spends - total_refunds
        funds = total_funds - total_withdraw

        card = Card.objects.select_for_update().get(id=self.id)
        card.fb_spends = fb_spends
        card.funds = funds
        card.save(update_fields=['fb_spends', 'funds'])

    @classmethod
    def get_type_by_display_string(cls, display_string: str) -> Tuple[int, str]:
        """
        Gets credit card type given name.
        """
        name = display_string[:-5]
        code = Card.CC_TYPES_DICT.get(name)
        if code:
            return code, name
        return CC_TYPE_GENERIC, 'Generic'

    @classmethod
    def get_type_by_number(cls, number: str) -> Tuple[int, str]:
        """
        Gets credit card type given number.
        """
        number = get_digits(number)
        for code, record in CC_TYPES:
            if re.match(record['regex'], number):
                return code, record['title']
        return CC_TYPE_GENERIC, 'Generic'

    @classmethod
    @transaction.atomic
    def create(
        cls,
        number,
        adaccount_card,
        created_by: User,
        comment: str = None,
        created_at: datetime.datetime = None,
        **kwargs,
    ):
        card_type_code, card_type_title = cls.get_type_by_number(number)
        display_string = f'{card_type_title}*{number[-4:]}'

        if created_at is None:
            created_at = timezone.now()

        credit_card_data = {
            'created_at': created_at,
            'card_type': card_type_code,
            'display_string': display_string,
            'comment': comment,
            'created_by_id': created_by.id,
            'number': number,
        }
        credit_card = cls.objects.create(**credit_card_data)

        if 'initial_balance' in kwargs:
            credit_card = cls.objects.select_for_update().get(pk=credit_card.pk)

            balance = kwargs.pop('initial_balance')
            if balance:
                account = Account.objects.select_for_update().get(id=adaccount_card.adaccount.account_id)
                account.add_cart_balance(created_by, balance, adaccount_card.adaccount)
                reason = f'Initial TopUp by {created_by.display_name} on Card Add'
                adaccount_card.create_transaction(
                    created_by=created_by,
                    card=credit_card,
                    amount=balance,
                    now=created_at,
                    reason=reason,
                    charge_type='topup',
                )
                credit_card.funds = credit_card.funds + balance  # F() не надо, так как select_for_update
                credit_card.save(update_fields=['funds'])
                AdAccountCreditCard.objects.filter(credential_id=adaccount_card.credential_id).update(card=credit_card)
                AdAccountTransaction.objects.filter(adaccount_card__credential_id=adaccount_card.credential_id).update(
                    card=credit_card
                )
                adaccount_card.recalc_spends()
                credit_card.recalc_spends()

        Action.create(
            action_datetime=timezone.now(),
            actor=created_by,
            verb='Created credit card',
            action_object=credit_card,
            target_object=adaccount_card.adaccount,
            data=credit_card_data,
        )
        return credit_card

    @classmethod
    @transaction.atomic
    def update(
        cls, pk, updated_by=None, **kwargs,
    ):
        now = timezone.now()
        credit_card = cls.objects.select_for_update().get(pk=pk)

        if 'spend' in kwargs and 'is_active' in kwargs:
            # Fixing total spends at card closing
            correction = credit_card.fb_spends - kwargs['spend']
            if correction:
                reason = f'Correction transaction on card closing by {updated_by.display_name}'
                charge_type = 'topup' if correction > 0 else 'payment'
                credit_card.create_transaction(
                    created_by=updated_by, amount=abs(correction), now=now, reason=reason, charge_type=charge_type
                )
                credit_card.recalc_spends()

        for field_name, value in kwargs.items():
            setattr(credit_card, field_name, value)

        changed_data = credit_card.get_changed_data()
        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            Action.create(
                action_datetime=now,
                actor=updated_by,
                verb='Credit card updated',
                action_object=credit_card,
                data=changed_data,
            )
            credit_card.save(update_fields=update_fields)

        return credit_card

    @transaction.atomic
    def create_transaction(self, amount, charge_type, now, reason, created_by=None):
        # TODO: Action log
        AdAccountTransaction.objects.create(
            card=self,
            created_by=created_by,
            currency='USD',
            charge_type=charge_type,
            payment_option='credit_card',
            status='completed',
            amount=amount,
            billed_at=now,
            reason=reason,
        )


class AdAccountLog(models.Model):
    """
    Модель для хранения времени в каждом статусе для подсчета статы по статусам
    + возврата статуса при некоторых действиях с акком + Лог менеджеров акка
    """

    STATUS = 0
    MANAGER = 1
    LOG_TYPE_CHOICES = (
        (STATUS, 'Status'),
        (MANAGER, 'Manager'),
    )

    adaccount = models.ForeignKey(AdAccount, on_delete=models.CASCADE, db_index=True)

    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)

    log_type = models.PositiveSmallIntegerField(choices=LOG_TYPE_CHOICES, default=STATUS, db_index=True)

    status = models.PositiveIntegerField(
        choices=AdAccount.ADACCOUNT_STATUS_CHOICES, null=True, blank=True, db_index=True
    )
    manager = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    changed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name='adaccount_logs'
    )

    def __str__(self):
        return f'{self.get_log_type_display()} Log({self.id})'

    class Meta:
        index_together = (('start_at', 'end_at'), ('adaccount', 'status', 'log_type', 'end_at'))

    @classmethod
    def log_change(cls, adaccount, now, log_type, **kwargs):
        try:
            log = cls.objects.select_for_update().get(adaccount=adaccount, log_type=log_type, end_at__isnull=True)
            log.end_at = now
            update_fields = ['end_at']
            log.save(update_fields=update_fields)
        except AdAccountLog.DoesNotExist:
            pass

        log_data = {
            'adaccount': adaccount,
            'start_at': now,
            'log_type': log_type,
        }
        for key, value in kwargs.items():
            log_data[key] = value
        cls.objects.create(**log_data)


class AdAccountTransaction(models.Model):
    adaccount = models.ForeignKey(AdAccount, on_delete=models.CASCADE, db_index=True, null=True, blank=True)
    transaction_id = models.CharField(max_length=64, db_index=True, default=uuid.uuid4)
    card = models.ForeignKey(Card, on_delete=models.SET_NULL, db_index=True, null=True, blank=True)
    adaccount_card = models.ForeignKey(
        AdAccountCreditCard, on_delete=models.CASCADE, db_index=True, null=True, blank=True
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    start_at = models.DateTimeField(_('Billing start time'), db_index=True, null=True, blank=True)
    start_at_ts = models.PositiveIntegerField(_('Billing start timestamp'), db_index=True, null=True, blank=True)
    end_at = models.DateTimeField(_('Billing end time'), db_index=True, null=True, blank=True)
    end_at_ts = models.PositiveIntegerField(_('Billing end timestamp'), db_index=True, null=True, blank=True)
    billed_at = models.DateTimeField(_('Billed at'), db_index=True)
    created_at = models.DateTimeField(_('Created at'), db_index=True, auto_now_add=True)
    reason = models.CharField(_('Billing reason'), max_length=1024)
    charge_type = models.CharField(_('Charge type'), max_length=32)
    product_type = models.CharField(_('Product type'), max_length=32, null=True, blank=True)
    payment_option = models.CharField(_('Payment option'), max_length=32)
    status = models.CharField(_('Payment status'), max_length=32)
    tracking_id = models.CharField(_('tracking_id'), max_length=32, null=True, blank=True)
    transaction_type = models.CharField(_('Transaction type'), max_length=32, null=True, blank=True)
    tx_type = models.IntegerField(_('TX type'), default=3)  # ХЗ, че это
    vat_invoice_id = models.CharField(_('VAT invoice ID'), max_length=32, null=True, blank=True)
    data = models.JSONField(_('RAW transaction data'), null=True, blank=True)

    def __str__(self):
        return f'Transaction #{self.transaction_id} on {self.amount}{self.currency}'

    class Meta:
        unique_together = ('adaccount', 'transaction_id')
        index_together = ('adaccount', 'transaction_id')


class Ad(LogChangedMixin):
    AD_STATUS_CHOICES = (('ACTIVE', 'Active'), ('PAUSED', 'Paused'), ('DELETED', 'Deleted'), ('ARCHIVED', 'Archived'))
    AD_EFFECTIVE_STATUS = (
        'ACTIVE',
        'PAUSED',
        'DELETED',
        'PENDING_REVIEW',
        'DISAPPROVED',
        'PREAPPROVED',
        'PENDING_BILLING_INFO',
        'CAMPAIGN_PAUSED',
        'ARCHIVED',
        'ADSET_PAUSED',
        'IN_PROCESS',
        'WITH_ISSUES',
    )
    AD_EFFECTIVE_STATUS_CHOICES = (
        (status, status.lower().capitalize().replace('_', ' ')) for status in AD_EFFECTIVE_STATUS
    )

    # account = models.ForeignKey(Account, on_delete=models.PROTECT)
    adaccount = models.ForeignKey(AdAccount, on_delete=models.CASCADE)
    ad_id = models.BigIntegerField(_('FB ad id'))
    page = models.ForeignKey(FBPage, on_delete=models.CASCADE, null=True, blank=True, related_name='ads')
    name = models.CharField(_('Ad name'), max_length=512)
    status = models.CharField(_('Ad status'), default='ACTIVE', choices=AD_STATUS_CHOICES, max_length=12)
    effective_status = models.CharField(
        _('Ad effective status'), choices=AD_EFFECTIVE_STATUS_CHOICES, default='ACTIVE', max_length=24
    )
    ad_review_feedback = models.JSONField(_('Review Feedback'), max_length=4096, null=True, blank=True)
    ad_review_feedback_code = models.CharField(_('Review Feedback code'), max_length=256, null=True, blank=True)
    ad_review_feedback_text = models.CharField(_('Review Feedback text'), max_length=4096, null=True, blank=True)
    creative_id = models.BigIntegerField(_('FB creative id'))
    story_id = models.CharField(_('FB story id'), max_length=256, null=True, blank=True)
    ad_url = models.URLField(_('Ad URL'), null=True, blank=True, max_length=1024)
    total_comments = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    disable_check = models.BooleanField(default=False)

    fieldtracker = FieldTracker()

    class Meta:
        unique_together = ('adaccount', 'ad_id', 'creative_id')

    def __str__(self):
        return self.name

    @classmethod
    @transaction.atomic
    def create(
        cls,
        adaccount: AdAccount,
        ad_id: int,
        name: str,
        status: int,
        effective_status: str,
        creative_id: int,
        story_id: int,
        **kwargs,
    ):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        ad_data = {
            'adaccount_id': adaccount.id,
            'ad_id': ad_id,
            'name': name,
            'status': status,
            'effective_status': effective_status,
            'creative_id': creative_id,
            'story_id': story_id,
            **kwargs,
        }
        ad = cls.objects.create(**ad_data)

        Action.create(action_datetime=now, verb='created ad', action_object=ad, target_object=adaccount, data=ad_data)
        # TODO: чекать только новые и активные. Старые и неактивные не трогать.
        if ad.ad_url:
            ad.check_url()
        # TODO: ad log
        # AdAccountLog.log_change(adaccount=adaccount, now=now, status=adaccount.status)
        return ad

    @classmethod
    @transaction.atomic
    def update(cls, pk: int, action_verb: str, **kwargs):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        updated_by = kwargs.pop('updated_by') if 'updated_by' in kwargs else None
        ad = cls.objects.select_for_update().get(pk=pk)

        if 'effective_status' in kwargs and ad.effective_status != kwargs['effective_status']:
            # Пишем лог + нотификация
            ad.change_effective_status(kwargs.pop('effective_status'), changed_by=updated_by)

        for field_name, value in kwargs.items():
            setattr(ad, field_name, value)

        changed_data = ad.get_changed_data()

        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            ad.save(update_fields=update_fields)
            if ad.ad_url and 'ad_url' in update_fields:
                ad.check_url()
            Action.create(
                action_datetime=now, verb=action_verb, action_object=ad, target_object=ad.adaccount, data=changed_data
            )
        return ad

    def check_url(self):
        if self.adaccount.account.manager_id in [38, 39]:
            return

        ad_domain = urlparse(self.ad_url).netloc
        extracted = tldextract.extract(ad_domain)
        domain = f'{extracted.domain}.{extracted.suffix}'
        # if 'myshopify.com' not in ad_domain:
        if not Domain.objects.filter(name=domain).exists():
            message = render_to_string('ads/wrong_domain.html', {'ad': self})
            data = {'message': message, 'account_id': self.adaccount.account_id, 'adaccount_id': self.adaccount_id}

            recipients = list(User.get_recipients(roles=[User.ADMIN, User.FINANCIER, User.MANAGER]))
            recipients.append(self.adaccount.account.manager)
            for recipient in recipients:
                Notification.create(
                    recipient=recipient, level=Notification.WARNING, category=Notification.AD, data=data, sender=None,
                )

    def change_effective_status(self, new_status: int, changed_by: Optional[User] = None) -> None:
        # if new_status == 'active' and self.ad_url:
        #     self.check_url()

        self.effective_status = new_status
        # надо для учета статы + записать в статистику
        # AdAccountLog.log_change(adaccount=self, status=new_status, now=now)
        if self.adaccount.account.manager:
            message = render_to_string('ads/change_effective_status.html', {'ad': self})
            data = {'message': message, 'account_id': self.adaccount.account_id, 'adaccount_id': self.adaccount_id}
            Notification.create(
                recipient=self.adaccount.account.manager,
                level=Notification.CRITICAL,
                category=Notification.AD,
                data=data,
                sender=changed_by,
            )


class UserRequest(ConcurrentTransitionMixin, LogChangedMixin):
    # STATUS_CHOICES
    WAITING = 0
    PROCESSING = 10
    DECLINED = 20
    APPROVED = 50

    # REQUEST_TYPE_CHOICES
    ACCOUNTS = 'accounts'
    MONEY = 'money'
    SETUP = 'setup'
    FIX = 'fix'

    STATUS_CHOICES = (
        (WAITING, _('Waiting')),
        (DECLINED, _('Declined')),
        (APPROVED, _('Approve')),
        (PROCESSING, _('Processing')),
    )

    REQUEST_TYPE_CHOICES = (
        (ACCOUNTS, _('Accounts request')),
        (MONEY, _('Money request')),
        (SETUP, _('Setup request')),
        (FIX, _('Fix request')),
    )
    user = models.ForeignKey(User, related_name='user_requests', on_delete=models.PROTECT)
    status = FSMIntegerField(_('Request status'), choices=STATUS_CHOICES, default=WAITING)
    comment = models.CharField(_('Comment'), max_length=512, null=True, blank=True)
    request_type = models.CharField(_('Request type'), choices=REQUEST_TYPE_CHOICES, default='money', max_length=32)
    request_data = models.JSONField(_('Request data'), encoder=DjangoJSONEncoder)

    processed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='processed_user_requests', null=True, blank=True
    )
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(_('Done datetime'))

    fieldtracker = FieldTracker()

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.request_type} request: {self.id}'

    def notify_create(self):
        context = {'request': self}
        data = {'request_type': self.request_type, 'request_id': self.id}
        getattr(self, f'notify_create_{self.request_type}')(context, data)

    def notify_create_setup(self, context: Dict[str, Any], data: Dict[str, Any]):
        account_id = self.request_data.get('account_id')
        if account_id:
            account = Account.objects.get(id=account_id)
            context['account'] = account
            data['account_id'] = account_id

        data['message'] = render_to_string("user_requests/create_setup.html", context)
        recipients = User.get_recipients(roles=[User.SETUPER])
        for recipient in recipients:
            # noinspection PyTypeChecker
            Notification.create(
                recipient=recipient,
                level=Notification.WARNING,
                category=Notification.REQUEST,
                data=data,
                sender=self.user,
            )

    def notify_create_accounts(self, context: Dict[str, Any], data: Dict[str, Any]):
        data['message'] = render_to_string("user_requests/create_accounts.html", context)
        recipients = User.get_recipients(roles=[User.MANAGER])
        for recipient in recipients:
            # noinspection PyTypeChecker
            Notification.create(
                recipient=recipient,
                level=Notification.WARNING,
                category=Notification.REQUEST,
                data=data,
                sender=self.user,
            )

    def notify_create_fix(self, context: Dict[str, Any], data: Dict[str, Any]):
        account_id = self.request_data['account_id']
        # if account_id:
        account = Account.objects.get(id=account_id)
        context['account'] = account
        data['account_id'] = account_id

        data['message'] = render_to_string("user_requests/create_fix.html", context)
        if context['request'].request_data['category'] == 'docs' and account.supplier:
            recipients = [account.supplier]
        else:
            recipients = User.get_recipients(roles=[User.FINANCIER])

        for recipient in recipients:
            Notification.create(
                recipient=recipient,
                level=Notification.CRITICAL,
                category=Notification.REQUEST,
                data=data,
                sender=self.user,
            )

    def notify_create_money(self, context: Dict[str, Any], data: Dict[str, Any]):
        account_id = self.request_data.get('account_id')
        if account_id:
            account = Account.objects.get(id=account_id)
            context['account'] = account
            data['account_id'] = account_id

        data['message'] = render_to_string("user_requests/create_money.html", context)
        recipients = User.get_recipients(roles=[User.FINANCIER])
        for recipient in recipients:
            # noinspection PyTypeChecker
            Notification.create(
                recipient=recipient,
                level=Notification.WARNING,
                category=Notification.REQUEST,
                data=data,
                sender=self.user,
            )

    def notify_approved(self):
        data = {'request_type': self.request_type, 'request_id': self.id}
        context = {'request': self}
        account_id = self.request_data.get('account_id')
        if account_id:
            account = Account.objects.get(id=account_id)
            context['account'] = account
            data['account_id'] = account_id

        data['message'] = render_to_string("user_requests/approved.html", context)
        # noinspection PyTypeChecker
        Notification.create(
            recipient=self.user,
            level=Notification.INFO,
            category=Notification.REQUEST,
            data=data,
            sender=self.processed_by,
        )

    def notify_declined(self):
        context = {'request': self}
        data = {'request_type': self.request_type, 'request_id': self.id}
        account_id = self.request_data.get('account_id')
        if account_id:
            account = Account.objects.get(id=account_id)
            context['account'] = account
            data['account_id'] = account_id

        data['message'] = render_to_string("user_requests/declined.html", context)
        # noinspection PyTypeChecker
        Notification.create(
            recipient=self.user,
            level=Notification.INFO,
            category=Notification.REQUEST,
            data=data,
            sender=self.processed_by,
        )

    @classmethod
    @transaction.atomic
    def create(cls, user: User, request_type: str, request_data: Dict[str, Any], comment: str, notify=True):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        action_data = {'actor': user, 'action_datetime': now, 'verb': f'requested {request_type}'}

        account_id = request_data.get('account_id')

        if account_id is not None:
            if request_type == 'setup':
                account = Account.objects.get(id=account_id)
                if account.status != Account.SETUP:
                    account = Account.update(
                        pk=account_id,
                        updated_by=user,
                        action_verb='updated on setup request created',
                        updated_at=now,
                        status=Account.SETUP,
                    )
            elif request_type == 'money':
                # лочим запись и обновляем
                account = Account.objects.select_for_update().get(id=account_id)
                account.funds_wait = F('funds_wait') + Decimal(request_data['amount'])
                account.save(update_fields=['funds_wait'])

            else:
                account = Account.objects.get(id=account_id)

            action_data['action_object'] = account

        user_request = cls.objects.create(
            user=user,
            request_type=request_type,
            request_data=request_data,
            comment=comment,
            created_at=now,
            updated_at=now,
        )
        # надо для учета статы + записать в статистику
        UserRequestLog.log_change(user_request=user_request, now=now, status=UserRequest.WAITING)

        action_data['action_object'] = user_request
        action_data['data'] = request_data

        Action.create(**action_data)
        if notify:
            user_request.notify_create()
        return user_request

    @classmethod
    @transaction.atomic
    def update(cls, pk: int, updated_by: User, status: int, request_data: Dict[str, Any], notify=True):
        now = timezone.now()  # Для того, чтобы время было одинаковое везде
        user_request = cls.objects.select_for_update().get(pk=pk)
        action_verb = f'user {user_request.request_type} request changed'

        user_request.request_data.update(request_data)
        user_request.processed_by = updated_by
        user_request.updated_at = now

        if status == UserRequest.APPROVED:
            user_request.approve(updated_by, now=now, notify=notify)
            action_verb = f'user {user_request.request_type} request approved'

        elif status == UserRequest.PROCESSING:
            user_request.processing(updated_by)

        elif status == UserRequest.DECLINED:
            user_request.decline(updated_by, notify=notify)
            action_verb = f'user {user_request.request_type} request declined'

        changed_data = user_request.get_changed_data()
        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            user_request.save(update_fields=update_fields)

        account_id = user_request.request_data.get('account_id')
        if account_id:
            if user_request.request_type == 'setup' and status != UserRequest.PROCESSING:
                account = Account.objects.get(id=account_id)
                if account.status == Account.SETUP:
                    Account.update(
                        pk=account_id,
                        updated_by=updated_by,
                        action_verb='updated on request done',
                        status=Account.READY,
                    )

            if user_request.request_type == 'money':
                # лочим запись и обновляем
                account = Account.objects.select_for_update().get(id=account_id)
                account.funds_wait = F('funds_wait') - Decimal(user_request.request_data.get('amount'))
                account.save(update_fields=['funds_wait'])

        UserRequestLog.log_change(user_request=user_request, status=user_request.status, now=now)
        Action.create(
            actor=updated_by, action_datetime=now, verb=action_verb, action_object=user_request, data=changed_data
        )
        return user_request

    @transition(field='status', source=[WAITING, PROCESSING], target=APPROVED)
    def approve(self, updated_by, now, notify):
        if self.request_type == 'money':
            account_id = self.request_data.get('account_id')
            adaccount_id = self.request_data.get('adaccount_id')

            if account_id is not None:
                # лочим запись и обновляем
                account = Account.objects.select_for_update().get(id=account_id)
                actual_amount = (
                    self.request_data.get('actual_amount')
                    if self.request_data.get('actual_amount') is not None
                    else self.request_data.get('amount')
                )
                account.last_funded = Decimal(actual_amount)
                account.total_funds = F('total_funds') + Decimal(actual_amount)
                account.save(update_fields=['total_funds', 'last_funded'])

                adaccount = None
                if adaccount_id:
                    adaccount = AdAccount.objects.get(id=adaccount_id)

                if card_id := self.request_data.get('card_id'):
                    adaccount_card = AdAccountCreditCard.objects.select_for_update().get(id=card_id)
                    amount = Decimal(self.request_data.get('actual_amount'))
                    action = 'TopUp' if amount >= 0 else 'Withdraw'
                    reason = f'{action} by {updated_by.display_name} on User request #{self.id}'
                    adaccount_card.create_transaction(
                        card=adaccount_card.card,
                        created_by=updated_by,
                        amount=abs(amount),
                        now=now,
                        reason=reason,
                        charge_type=action.lower(),
                    )
                    adaccount_card.recalc_spends()
                    if adaccount_card.card:
                        adaccount_card.card.recalc_spends()

                UserAccountDayStat.upsert(
                    date=now.date(),
                    account_id=account.id,
                    user_id=account.manager.id if account.manager else None,
                    campaign_id=adaccount.campaign_id
                    if (adaccount and adaccount.campaign_id)
                    else account.campaign_id,
                    spend=Decimal('0.00'),
                    profit=Decimal('0.00'),
                    funds=Decimal(actual_amount),
                    clicks=Decimal('0.00'),
                    visits=Decimal('0.00'),
                    revenue=Decimal('0.00'),
                    leads=Decimal('0.00'),
                    cost=Decimal('0.00'),
                    payment=Decimal('0.00'),
                )

        if self.user_id != updated_by.id and notify:
            self.notify_approved()

    @transition(field='status', source=[WAITING, PROCESSING], target=DECLINED)
    def decline(self, updated_by, notify):
        self.request_data['status_comment'] = (
            'Cancelled by user'
            if (self.user_id == updated_by.id and not self.request_data.get('status_comment'))
            else self.request_data.get('status_comment')
        )
        if self.user_id != updated_by.id and notify:
            self.notify_declined()

    @transition(field='status', source=[WAITING], target=PROCESSING)
    def processing(self, updated_by):
        pass


class UserRequestLog(models.Model):
    """
    Модель для хранения времени в каждом статусе для подсчета статы по статусам
    """

    user_request = models.ForeignKey(UserRequest, on_delete=models.CASCADE, db_index=True)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.PositiveIntegerField(choices=UserRequest.STATUS_CHOICES, null=True, blank=True, db_index=True)

    class Meta:
        index_together = (('start_at', 'end_at'), ('user_request', 'status'))

    @classmethod
    def log_change(cls, user_request, now, **kwargs):
        try:
            log = cls.objects.select_for_update().get(user_request=user_request, end_at__isnull=True)
            log.end_at = now
            log.save(update_fields=['end_at'])
        except UserRequestLog.DoesNotExist:
            pass
        cls.objects.create(user_request=user_request, start_at=now, status=kwargs['status'])


class Notification(models.Model):
    INFO = 0
    WARNING = 10
    CRITICAL = 20
    LEVEL_CHOICES = ((INFO, 'info'), (WARNING, 'warning'), (CRITICAL, 'critical'))

    AD = 'ad'
    ACCOUNT = 'account'
    ADACCOUNT = 'adaccount'
    REQUEST = 'request'
    FINANCE = 'finance'
    SYSTEM = 'system'
    PROXY = 'proxy'
    PAGE = 'page'
    TRACKER = 'tracker'

    NOTIFICATION_CATEGORY_CHOICES = (
        (ACCOUNT, 'account'),
        (ADACCOUNT, 'adaccount'),
        (REQUEST, 'request'),
        (AD, 'ad'),
        (FINANCE, 'finance'),
        (SYSTEM, 'system'),
        (PROXY, 'proxy'),
        (PAGE, 'page'),
    )
    sender = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='senders_notifications'
    )
    recipient = models.ForeignKey(User, on_delete=models.PROTECT)
    category = models.CharField(
        _('Notification category'), max_length=64, choices=NOTIFICATION_CATEGORY_CHOICES, default=ACCOUNT
    )
    level = models.PositiveSmallIntegerField(_('Notification level'), choices=LEVEL_CHOICES, default=INFO)
    created_at = models.DateTimeField(default=timezone.now)
    readed_at = models.DateTimeField(null=True, blank=True)
    sended_at = models.DateTimeField(null=True, blank=True)
    sended_email_at = models.DateTimeField(null=True, blank=True)
    sended_telegram_at = models.DateTimeField(null=True, blank=True)
    data = models.JSONField(encoder=DjangoJSONEncoder)

    def __str__(self):
        return f'{self.category} from {self.sender} to {self.recipient}'

    class Meta:
        ordering = ('-created_at',)
        index_together = ('id', 'recipient')

    @classmethod
    @transaction.atomic
    def create(cls, recipient: User, level: int, category: str, data: dict, sender: Optional[User] = None):
        now = timezone.now()
        notification_data = {
            'recipient': recipient,
            'level': level,
            'category': category,
            'data': data,
            'created_at': now,
        }
        if sender is not None:
            notification_data['sender'] = sender

        notification = cls.objects.create(**notification_data)

        # Send notifications
        if notification.recipient.is_active:
            # Send to wscreate_links
            notification.send('websocket')
            # Send to other channels
            for subscription in notification.recipient.notificationsubscription_set.filter(level=notification.level):
                notification.send(subscription.channel)
        return notification

    def send(self, channel='websocket'):
        if channel == 'telegram':
            self.send_telegram()
        elif channel == 'email':
            self.send_email()
        elif channel == 'websocket':
            self.send_websocket()

    def send_websocket(self):
        from core.tasks.notifications import notify_websocket

        # обрабатываем только в конце транзакции
        transaction.on_commit(lambda: notify_websocket.delay(notification_id=self.id))

    def send_email(self):
        if self.recipient.email:
            from core.tasks.notifications import notify_email

            # обрабатываем только в конце транзакции
            transaction.on_commit(lambda: notify_email.delay(notification_id=self.id))

    def send_telegram(self):
        if self.recipient.telegram_id:
            from core.tasks.notifications import notify_telegram

            # обрабатываем только в конце транзакции
            transaction.on_commit(lambda: notify_telegram.delay(notification_id=self.id))


class NotificationSubscription(models.Model):
    CHANNEL_CHOICES = (('email', 'Email'), ('telegram', 'Telegram'))
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    level = models.PositiveSmallIntegerField(_('Notification level'), choices=Notification.LEVEL_CHOICES)
    channel = models.CharField(_('Channel'), choices=CHANNEL_CHOICES, max_length=32)

    class Meta:
        unique_together = ('user', 'level', 'channel')


class Flow(models.Model):
    flow_id = models.PositiveIntegerField()
    flow_name = models.CharField(max_length=255)
    status = models.CharField(max_length=64)

    def __str__(self):
        return self.flow_name


class Domain(models.Model):
    domain_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=255, db_index=True)
    is_banned = models.BooleanField(default=False)
    is_internal = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class UserKPI(models.Model):
    METRIC_CHOICES = (
        ('profit', 'Profit'),
        ('leads', 'Leads'),
    )

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    metric = models.CharField(default='profit', max_length=32)
    value = models.PositiveIntegerField()
    start_at = models.DateField(db_index=True)
    end_at = models.DateField(db_index=True)

    def get_profit(self, queryset):
        stats = queryset.annotate(full_spend=Case(When(spend=0, then=F('cost')), default=F('spend'))).aggregate(
            total_profit=Sum(F('revenue') - F('full_spend'))
        )
        return stats.get('total_profit') or Decimal('0.00')

    def get_leads(self, queryset):
        stats = queryset.aggregate(total_leads=Sum('leads'))
        return stats.get('total_leads') or 0

    @property
    def current_value(self):
        queryset = UserAccountDayStat.objects.filter(date__gte=self.start_at, date__lte=self.end_at).exclude(
            Q(user_id__in=[38, 39]) | Q(campaign__name__icontains='youtube')
        )
        if self.user:
            queryset = queryset.filter(user=self.user)

        return getattr(self, f'get_{self.metric}')(queryset)


# STATS MODELS
class FlowDayStat(models.Model):
    """
    Сырые Данные по стате Flow из трекера
    """

    flow = models.ForeignKey(Flow, on_delete=models.PROTECT)
    date = models.DateField(db_index=True)
    visits = models.PositiveIntegerField(_('Visits'), default=0)
    leads = models.PositiveIntegerField(_('Leads'), default=0)
    clicks = models.PositiveIntegerField(_('Clicks'), default=0)
    revenue = models.DecimalField(_('Revenue'), max_digits=10, decimal_places=2, default=0)
    cost = models.DecimalField(_('Cost'), max_digits=10, decimal_places=2, default=0)
    profit = models.DecimalField(_('Profit'), max_digits=10, decimal_places=2, default=0)
    payment = models.DecimalField(_('Payment'), max_digits=10, decimal_places=2, default=0)  # Не используется

    roi = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ctr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cv = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cpv = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    epv = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    epc = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('flow', 'date')


class CampaignDayStat(models.Model):
    """
    Сырые данные по стате кампаний из трекера
    """

    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    date = models.DateField(db_index=True)

    visits = models.PositiveIntegerField(_('Visits'), default=0)
    leads = models.PositiveIntegerField(_('Leads'), default=0)
    clicks = models.PositiveIntegerField(_('Clicks'), default=0)
    revenue = models.DecimalField(_('Revenue'), max_digits=10, decimal_places=2, default=0)
    cost = models.DecimalField(_('Cost'), max_digits=10, decimal_places=2, default=0)
    profit = models.DecimalField(_('Profit'), max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('campaign', 'date')


class AdAccountDayStat(models.Model):
    """
    Сырые данные по спенду
    """

    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    adaccount = models.ForeignKey(AdAccount, on_delete=models.CASCADE)
    date = models.DateField(db_index=True)
    clicks = models.PositiveIntegerField(_('clicks'), default=0)
    spend = models.DecimalField(_('Spend'), max_digits=10, decimal_places=2, default=0)
    # funds = models.DecimalField(_('Funds'), max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('account', 'adaccount', 'date')

    def __str__(self):
        return f'AdAccount Day Stat {self.adaccount} - {self.account.display_name} - {self.date}'

    @classmethod
    @transaction.atomic
    def create(cls, account, adaccount, date, clicks, spend):
        adaccount_day_stat = cls.objects.create(
            account=account, adaccount=adaccount, date=date, clicks=clicks, spend=spend
        )
        return adaccount_day_stat

    @classmethod
    @transaction.atomic
    def update(cls, pk, clicks, spend) -> Tuple:
        current_stats = AdAccountDayStat.objects.select_for_update().get(pk=pk)

        prev_stats = copy(current_stats)

        current_stats.clicks = clicks
        current_stats.spend = spend
        current_stats.save()

        return prev_stats, current_stats


class UserAdAccountDayStat(models.Model):
    """
    Cтата по аккаунту и юзеру по дням
    Обязательно создать индекс, миграция 0254_auto_20200227_1419.py
    "CREATE UNIQUE INDEX date_acc_adacc_user_id ON core_useradaccountdaystat
    (date, account_id, adaccount_id, COALESCE(user_id, -1))",
    """

    date = models.DateField(db_index=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, db_index=True)
    adaccount = models.ForeignKey(AdAccount, on_delete=models.CASCADE, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    # FB
    clicks = models.IntegerField(_('clicks'), default=0)  # Тут бывают коррекции у ФБ и клики могут быть отрицательные
    spend = models.DecimalField(_('Spend'), max_digits=10, decimal_places=2, default=0)
    # funds = models.DecimalField(_('Funds'), max_digits=10, decimal_places=2, default=0)

    @classmethod
    def upsert(
        cls,
        date: datetime.date,
        account_id: int,
        adaccount_id: int,
        user_id: Optional[Type[int]],
        spend: Decimal,
        clicks: int,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO core_useradaccountdaystat (
                    date, account_id, adaccount_id, user_id, spend, clicks
                ) VALUES (
                    %(date)s,  %(account_id)s, %(adaccount_id)s,  %(user_id)s, %(spend)s,
                    %(clicks)s
                )
                ON CONFLICT (date, account_id, adaccount_id, COALESCE(user_id, -1))
                DO UPDATE SET
                    spend = core_useradaccountdaystat.spend + %(spend)s,
                    clicks = core_useradaccountdaystat.clicks + %(clicks)s
                """,
                {
                    'date': date,
                    'account_id': account_id,
                    'adaccount_id': adaccount_id,
                    'user_id': user_id,
                    'spend': spend,
                    'clicks': clicks,
                },
            )


class UserCampaignDayStat(models.Model):
    """
    Модель для хранения статы по юзерским кампаниям по дням
    Необходима в случае наличия кампаний, которые не привязаны к аккаунтам
    Да и просто для порядка
    Обязательно создать индекс, миграция 0256_auto_20200227_1451.py
    "CREATE UNIQUE INDEX date_camp_user_id ON core_usercampaigndaystat(date, campaign_id, COALESCE(user_id, -1))"
    """

    date = models.DateField(db_index=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    # Tracker
    visits = models.IntegerField(_('Visits'), default=0)
    leads = models.IntegerField(_('Leads'), default=0)
    clicks = models.IntegerField(_('Clicks'), default=0)
    revenue = models.DecimalField(_('Revenue'), max_digits=10, decimal_places=2, default=0)
    cost = models.DecimalField(_('Cost'), max_digits=10, decimal_places=2, default=0)
    profit = models.DecimalField(_('Profit'), max_digits=10, decimal_places=2, default=0)

    @classmethod
    def upsert(
        cls,
        date: datetime.date,
        campaign_id: Optional[Type[int]],
        user_id: Optional[Type[int]],
        clicks: int,
        visits: int,
        leads: int,
        revenue: Decimal,
        cost: Decimal,
        profit: Decimal,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO core_usercampaigndaystat (
                    date, campaign_id, user_id, clicks, visits, leads, revenue, cost,
                    profit
                ) VALUES (
                    %(date)s, %(campaign_id)s, %(user_id)s, %(clicks)s, %(visits)s, %(leads)s, %(revenue)s, %(cost)s,
                     %(profit)s
                )
                ON CONFLICT (date, campaign_id, COALESCE(user_id, -1))
                DO UPDATE SET
                    clicks = core_usercampaigndaystat.clicks + %(clicks)s,
                    visits = core_usercampaigndaystat.visits + %(visits)s,
                    leads = core_usercampaigndaystat.leads + %(leads)s,
                    revenue = core_usercampaigndaystat.revenue + %(revenue)s,
                    cost = core_usercampaigndaystat.cost + %(cost)s,
                    profit = core_usercampaigndaystat.profit + %(profit)s
                """,
                {
                    'date': date,
                    'campaign_id': campaign_id,
                    'user_id': user_id,
                    'clicks': clicks,
                    'visits': visits,
                    'leads': leads,
                    'revenue': revenue,
                    'cost': cost,
                    'profit': profit,
                },
            )


class UserAccountDayStat(models.Model):
    """
    Дневная стата по акку, юзеру, кампании
    CREATE UNIQUE INDEX date_acc_camp_user_id ON core_useraccountdaystat
    (date, COALESCE(account_id, -1), COALESCE(campaign_id, -1), COALESCE(user_id, -1))
    миграция 0258_auto_20200228_1111.py
    """

    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=True, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField(db_index=True)
    # FB spends
    spend = models.DecimalField(_('Spend'), max_digits=10, decimal_places=2, default=0)
    # Total funds
    funds = models.DecimalField(_('Funds'), max_digits=10, decimal_places=2, default=0)
    payment = models.DecimalField(_('Payment'), max_digits=10, decimal_places=2, default=0)
    # Tracker data
    visits = models.IntegerField(_('Visits'), default=0)
    leads = models.IntegerField(_('Leads'), default=0)
    clicks = models.IntegerField(_('Clicks'), default=0)
    revenue = models.DecimalField(_('Revenue'), max_digits=10, decimal_places=2, default=0)
    cost = models.DecimalField(_('Cost'), max_digits=10, decimal_places=2, default=0)
    # Calc data - revenue - spend
    profit = models.DecimalField(_('Profit'), max_digits=10, decimal_places=2, default=0)

    class Meta:
        index_together = ('account', 'campaign', 'date')

    @classmethod
    def upsert(
        cls,
        date: datetime.date,
        account_id: Optional[int],
        user_id: Optional[Type[int]],
        campaign_id: Optional[Type[int]],
        clicks: int,
        visits: int,
        leads: int,
        profit: Decimal,  # TODO: remove
        revenue: Decimal,
        cost: Decimal,
        spend: Decimal,
        funds: Decimal,
        payment: Decimal,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO core_useraccountdaystat (
                    date, account_id, user_id, campaign_id, clicks, visits, revenue, 
                    leads, cost, spend, funds, payment, profit
                ) VALUES (
                    %(date)s, %(account_id)s, %(user_id)s, %(campaign_id)s, %(clicks)s, %(visits)s, %(revenue)s,
                    %(leads)s, %(cost)s, %(spend)s, %(funds)s, %(payment)s, %(profit)s
                )
                ON CONFLICT (
                    date,
                    COALESCE(account_id, -1),
                    COALESCE(user_id, -1),
                    COALESCE(campaign_id, -1)
                )
                DO UPDATE SET
                    clicks = core_useraccountdaystat.clicks + %(clicks)s,
                    visits = core_useraccountdaystat.visits + %(visits)s,
                    revenue = core_useraccountdaystat.revenue + %(revenue)s,
                    leads = core_useraccountdaystat.leads + %(leads)s,
                    cost = core_useraccountdaystat.cost + %(cost)s,
                    spend = core_useraccountdaystat.spend + %(spend)s,
                    funds = core_useraccountdaystat.funds + %(funds)s,
                    payment = core_useraccountdaystat.payment + %(payment)s,
                    profit =
                        CASE
                          WHEN core_useraccountdaystat.spend = 0
                            THEN (core_useraccountdaystat.revenue + %(revenue)s) -
                                 (core_useraccountdaystat.cost + %(cost)s)
                          ELSE (core_useraccountdaystat.revenue + %(revenue)s) -
                                 (core_useraccountdaystat.spend + %(spend)s)
                        END;
                """,
                {
                    'date': date,
                    'account_id': account_id,
                    'user_id': user_id,
                    'campaign_id': campaign_id,
                    'clicks': clicks,
                    'visits': visits,
                    'leads': leads,
                    'cost': cost,
                    'revenue': revenue,
                    'profit': profit,
                    'funds': funds,
                    'payment': payment,
                    'spend': spend,
                },
            )


class UserDayStat(models.Model):
    """
    Дневная стата по акку, юзеру, кампании
    CREATE UNIQUE INDEX date_adacc_camp_user_id ON core_userdaystat
    (date, COALESCE(adaccount_id, -1), COALESCE(campaign_id, -1), COALESCE(user_id, -1))
    миграция 0459_auto_20210224_0942.py
    """

    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=True, blank=True)
    adaccount = models.ForeignKey(AdAccount, on_delete=models.CASCADE, null=True, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField(db_index=True)
    # FB spends
    spend = models.DecimalField(_('Spend'), max_digits=10, decimal_places=2, default=0)
    # Total funds
    funds = models.DecimalField(_('Funds'), max_digits=10, decimal_places=2, default=0)
    payment = models.DecimalField(_('Payment'), max_digits=10, decimal_places=2, default=0)
    # Tracker data
    visits = models.IntegerField(_('Visits'), default=0)
    leads = models.IntegerField(_('Leads'), default=0)
    clicks = models.IntegerField(_('Clicks'), default=0)
    revenue = models.DecimalField(_('Revenue'), max_digits=10, decimal_places=2, default=0)
    cost = models.DecimalField(_('Cost'), max_digits=10, decimal_places=2, default=0)
    # Calc data - revenue - spend
    profit = models.DecimalField(_('Profit'), max_digits=10, decimal_places=2, default=0)

    class Meta:
        index_together = ('adaccount', 'campaign', 'user', 'date')

    @classmethod
    def upsert(
        cls,
        date: datetime.date,
        account_id: Optional[int],
        adaccount_id: Optional[int],
        user_id: Optional[Type[int]],
        campaign_id: Optional[Type[int]],
        clicks: int,
        visits: int,
        leads: int,
        profit: Decimal,
        revenue: Decimal,
        cost: Decimal,
        spend: Decimal,
        funds: Decimal,
        payment: Decimal,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO core_userdaystat (
                    date, account_id, adaccount_id, user_id, campaign_id, clicks, visits, revenue, 
                    leads, cost, spend, funds, payment, profit
                ) VALUES (
                    %(date)s, %(account_id)s, %(adaccount_id)s, %(user_id)s, %(campaign_id)s, %(clicks)s, %(visits)s, %(revenue)s,
                    %(leads)s, %(cost)s, %(spend)s, %(funds)s, %(payment)s, %(profit)s
                )
                ON CONFLICT (
                    date,
                    COALESCE(account_id, -1),
                    COALESCE(adaccount_id, -1),
                    COALESCE(user_id, -1),
                    COALESCE(campaign_id, -1)
                )
                DO UPDATE SET
                    clicks = core_userdaystat.clicks + %(clicks)s,
                    visits = core_userdaystat.visits + %(visits)s,
                    revenue = core_userdaystat.revenue + %(revenue)s,
                    leads = core_userdaystat.leads + %(leads)s,
                    cost = core_userdaystat.cost + %(cost)s,
                    spend = core_userdaystat.spend + %(spend)s,
                    funds = core_userdaystat.funds + %(funds)s,
                    payment = core_userdaystat.payment + %(payment)s,
                    profit =
                        CASE
                          WHEN core_userdaystat.spend = 0
                            THEN (core_userdaystat.revenue + %(revenue)s) -
                                 (core_userdaystat.cost + %(cost)s)
                          ELSE (core_userdaystat.revenue + %(revenue)s) -
                                 (core_userdaystat.spend + %(spend)s)
                        END;
                """,
                {
                    'date': date,
                    'account_id': account_id,
                    'adaccount_id': adaccount_id,
                    'user_id': user_id,
                    'campaign_id': campaign_id,
                    'clicks': clicks,
                    'visits': visits,
                    'leads': leads,
                    'cost': cost,
                    'revenue': revenue,
                    'profit': profit,
                    'funds': funds,
                    'payment': payment,
                    'spend': spend,
                },
            )


def get_upload_path(instance, filename):
    ext = filename.split(".")[-1]
    ext = ext.lower()
    name = uuid.uuid4().hex
    return f"csv/{instance.user_id}/{instance.type}/{name}.{ext}"


class ProcessCSVTask(models.Model):
    STATUS_CHOICES = ((0, _('Created')), (1, _('Processing')), (2, _('Success')), (3, _('Error')))
    PAYMENTS = 'payments'
    LEADS = 'leads'

    CSV_TYPE_CHOICES = (
        (PAYMENTS, _('Payments')),
        (LEADS, _('Leads')),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to=get_upload_path)  # , validators=[FileValidator(allowed_mimetypes=['text/csv'])]
    # )
    type = models.CharField(_('CSV Type'), choices=CSV_TYPE_CHOICES, default=PAYMENTS, max_length=16)
    status = models.PositiveSmallIntegerField(_('Status'), choices=STATUS_CHOICES, default=0)
    created = models.DateTimeField(_('Created at'), auto_now_add=True)


def user_images_path(instance, filename):
    ext = filename.split(".")[-1]
    ext = ext.lower()
    name = uuid.uuid4().hex
    return f"{instance.user_id}/{name}.{ext}"


class UploadedImage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="images")
    size = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=255, default='Unknown')
    file = ProcessedImageField(
        [Transpose()],  # ResizeToFit(300, 300, upscale=False)],  # Какой там размер надо?
        format="JPEG",
        options={"quality": 95, "progressive": True, "optimize": True},
        upload_to=user_images_path,
    )
    thumbnail_s120 = ImageSpecField([ResizeToFill(120, 120)], source='file', format='JPEG', options={'quality': 95})
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def thumb_url(self):
        if not settings.DEBUG:
            return f"https://{settings.API_DOMAIN}{self.thumbnail_s120.url}"
        return f"http://localhost:8000{self.thumbnail_s120.url}"

    @property
    def url(self):
        if not settings.DEBUG:
            return f"https://{settings.API_DOMAIN}{self.file.url}"
        return f"http://localhost:8000{self.file.url}"


class UploadedVideo(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="videos")
    file = models.FileField(upload_to=user_images_path)
    size = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=255, default='Unknown')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def url(self):
        if not settings.DEBUG:
            return f"https://{settings.API_DOMAIN}{self.file.url}"
        return f"http://localhost:8000{self.file.url}"


class Rule(LogChangedMixin):
    ENTITY_TYPE_CHOICES = (
        ('AD', 'Ads'),
        ('ADSET', 'AdSets'),
        ('CAMPAIGN', 'Campaigns'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64)
    evaluation_spec = models.JSONField()
    execution_spec = models.JSONField()
    schedule_spec = models.JSONField()
    entity_type = models.CharField(max_length=10, default='AD', choices=ENTITY_TYPE_CHOICES)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('-id',)


class Leadgen(LogChangedMixin):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64)
    data = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('-id',)

    def __str__(self):
        return self.name


class PageLeadgen(LogChangedMixin):
    page = models.ForeignKey(FBPage, on_delete=models.CASCADE)
    leadgen = models.ForeignKey(Leadgen, on_delete=models.CASCADE)
    leadform_id = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_load = models.DateTimeField(default=timezone.now, null=True, blank=True)

    def __str__(self):
        return f'{self.page} {self.leadgen}'

    class Meta:
        unique_together = ('page', 'leadgen', 'leadform_id')


class LeadgenLead(models.Model):
    GENDER_CHOICES = (
        (None, 'Unknown'),
        (0, 'Male'),
        (1, 'Female'),
    )
    lead_id = models.BigIntegerField(null=True, blank=True)
    page = models.ForeignKey(FBPage, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    leadgen = models.ForeignKey(Leadgen, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    leadform_id = models.BigIntegerField(null=True, blank=True)

    uuid = models.UUIDField('User ID', default=uuid.uuid4, db_index=True, editable=False)
    email = models.EmailField("Email", null=True, blank=True, db_index=True)
    phone = models.CharField("Phone", max_length=32, null=True, blank=True, db_index=True)
    first_name = models.CharField('First Name', max_length=255, null=True, blank=True)
    last_name = models.CharField('Last name', max_length=255, null=True, blank=True)
    name = models.CharField('Name', max_length=255, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    country_code = models.CharField('Country code', max_length=2, null=True, blank=True)
    city = models.CharField('City', max_length=128, null=True, blank=True)
    zip = models.CharField('ZIP', max_length=32, null=True, blank=True)
    address = models.CharField('Address', max_length=255, null=True, blank=True)
    offer = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    network = models.CharField(max_length=32, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    referer = models.CharField(null=True, blank=True, max_length=4096)
    visit_id = models.CharField(null=True, blank=True, max_length=4096)
    ipaddress = models.GenericIPAddressField(null=True, blank=True)
    gender = models.PositiveSmallIntegerField(choices=GENDER_CHOICES, null=True, blank=True)

    raw_data = models.JSONField(null=True, blank=True)
    answers = ArrayField(base_field=models.JSONField(), null=True, blank=True)

    created_at = models.DateTimeField('Date added', default=timezone.now, db_index=True)
    exported_at = models.DateTimeField('Date exported', null=True, db_index=True)

    class Meta:
        verbose_name = _('Lead')
        verbose_name_plural = _('Leads')
        index_together = ('created_at', 'id')

    def __str__(self):
        return self.full_name or f'{self.uuid}'

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        if self.name:
            return self.name

        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    @property
    def clear_phone(self):
        from core.tasks.helpers import COUNTRY_PHONE

        phone = self.phone
        if self.phone is not None:
            prefix = COUNTRY_PHONE[self.country.code]
            if not self.phone.startswith(prefix):
                if self.phone.startswith(f'00{prefix[1:]}') or self.phone.startswith(f'0{prefix[1:]}0'):
                    phone = self.phone[4:]
                    phone = f'{prefix}{phone}'
                elif self.phone.startswith('+0'):
                    phone = self.phone[2:]
                    phone = f'{prefix}{phone}'
                elif self.phone.startswith('0') or self.phone.startswith('1'):
                    phone = self.phone[1:]
                    phone = f'{prefix}{phone}'
                elif self.phone.startswith(prefix[1:]):
                    phone = f'+{self.phone}'
                elif self.phone.startswith('+'):
                    phone = self.phone
                else:
                    phone = f'{prefix}{self.phone}'
        return phone

    @property
    def full_name(self):
        return self.get_full_name()

    def create_link(self, base_url, network='default', keyword=None):
        params = getattr(self, f'create_params_{network}')()

        if keyword is not None:
            params['utm_term'] = keyword

        parsed_url = urlparse(base_url)
        query = parsed_url.query
        query_dict = dict(parse_qsl(query))
        query_dict.update(params)
        updated_query = urlencode(query_dict)
        parsed_url = parsed_url._replace(query=updated_query)
        updated_url = urlunparse(parsed_url)
        return updated_url

    def create_params_default(self):
        params = {'var1': str(self.uuid), 'var2': self.get_full_name()}

        if self.email:
            params['var3'] = self.email

        if self.phone:
            params['var4'] = self.phone

        if self.city:
            params['var5'] = self.city

        if self.zip:
            params['var6'] = self.zip

        if self.address:
            params['var7'] = self.address

        return params

    def create_params_wlt(self):
        """
        &firstname=Test&lastname=Test&address=Test+ignore&zip=44754&city=Paris&email=dantae.kreighton%40aallaa.org&phone=513124124
        """
        params = {'var1': str(self.uuid), 'firstname': self.first_name, 'lastname': self.last_name}

        if self.email:
            params['email'] = self.email

        if self.phone:
            params['phone'] = self.phone

        if self.city:
            params['city'] = self.city

        if self.zip:
            params['zip'] = self.zip

        if self.address:
            params['address'] = self.address

        return params


class LeadgenLeadConversion(LogChangedMixin):
    lead = models.ForeignKey(LeadgenLead, on_delete=models.CASCADE)
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    payout = models.DecimalField(_('Payout'), decimal_places=2, max_digits=10, default=0)
    device_type = models.CharField(max_length=4, null=True, blank=True)
    device_brand = models.CharField(max_length=128, null=True, blank=True)
    device_model = models.CharField(max_length=128, null=True, blank=True)
    country = models.CharField(max_length=2, null=True, blank=True)
    city = models.CharField(max_length=128, null=True, blank=True)
    region = models.CharField(max_length=256, null=True, blank=True)
    isp = models.CharField(max_length=256, null=True, blank=True)
    connection_type = models.CharField(max_length=2, null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    browser_name = models.CharField(max_length=512, null=True, blank=True)
    offer_name = models.CharField(max_length=512, null=True, blank=True)
    language = models.CharField(max_length=6, null=True, blank=True)
    created_at = models.DateTimeField('Date added', default=timezone.now)
    exported_at = models.DateTimeField('Date exported', null=True, blank=True)


class LinkGroup(LogChangedMixin):
    # STATUS_CHOICES
    WAITING = 0
    PROCESSING = 10
    ERROR = 20
    SUCCESS = 50

    STATUS_CHOICES = (
        (WAITING, _('Waiting')),
        (PROCESSING, _('Processing')),
        (ERROR, _('Error')),
        (SUCCESS, _('Success')),
    )

    NETWORK_CHOICES = (
        ('default', 'Default'),
        ('wlt', 'WLT'),
    )

    uuid = models.UUIDField('Group UUID', default=uuid.uuid4, db_index=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    broadcast = models.ForeignKey('LinkGroup', on_delete=models.PROTECT, null=True, blank=True)
    name = models.CharField(max_length=64)
    base_url = models.URLField()
    network = models.CharField(default='default', max_length=32, choices=NETWORK_CHOICES)
    domain = models.ForeignKey(ShortifyDomain, on_delete=models.SET_NULL, null=True, blank=True)
    max_links = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, null=True, blank=True)
    total_links = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, default=WAITING)
    status_comment = models.CharField(max_length=1024, null=True, blank=True)
    filter_data = models.JSONField(encoder=DjangoJSONEncoder, default=dict)
    csv = models.FileField(max_length=1024, null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def click_rate(self):
        if self.total_links:
            cr = float(self.clicked_links) / float(self.total_links) * 100
            return Decimal(cr).quantize(Decimal('0.01'))
        return Decimal('0.00')

    def get_clicked_links(self):
        return self.link_set.filter(clicks__gt=0)

    @property
    def clicked_links(self):
        return self.get_clicked_links().count()

    class Meta:
        ordering = ('-created_at',)


class Link(LogChangedMixin):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    group = models.ForeignKey(LinkGroup, on_delete=models.CASCADE)
    leadgen_lead = models.ForeignKey(LeadgenLead, on_delete=models.CASCADE)
    url = models.URLField(max_length=1024)
    clicks = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    @cached_property
    def key(self):
        from core.utils import ALPHABET

        encoder = short_url.UrlEncoder(alphabet=ALPHABET)
        return encoder.encode_url(self.id)

    @property
    def short_url(self):
        # shortify_domain = self.group.domain
        shortify_domains = ShortifyDomain.objects.filter(is_banned=False, is_public=True).values_list(
            'domain', flat=True
        )
        domain = choice(list(shortify_domains))
        return f'https://{domain}/{self.key}'

    @classmethod
    @transaction.atomic
    def create(cls, user: User, group: LinkGroup, leadgen_lead: LeadgenLead):
        url = leadgen_lead.create_link(group.base_url, group.name)
        link = cls.objects.create(user=user, group=group, leadgen_lead=leadgen_lead, url=url)
        return link


class CampaignTemplate(LogChangedMixin):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    campaign = models.JSONField()

    class Meta:
        ordering = ('-id',)

    def __str__(self):
        return self.name


class AdsCreateTask(LogChangedMixin):
    # STATUS_CHOICES
    WAITING = 0
    PROCESSING = 10
    ERROR = 20
    SUCCESS = 50

    STATUS_CHOICES = (
        (WAITING, _('Waiting')),
        (PROCESSING, _('Processing')),
        (ERROR, _('Error')),
        (SUCCESS, _('Success')),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    template = models.ForeignKey(CampaignTemplate, on_delete=models.SET_NULL, null=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    adaccount = models.ForeignKey(AdAccount, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, default=WAITING)
    status_comment = models.CharField(max_length=1024, null=True, blank=True)
    adaccount_data = models.JSONField(encoder=DjangoJSONEncoder)
    campaign_data = models.JSONField(encoder=DjangoJSONEncoder)

    fieldtracker = FieldTracker()

    class Meta:
        ordering = ('-created_at',)

    @classmethod
    @transaction.atomic
    def create_many(cls, user: User, template: CampaignTemplate, adaccounts: List[Dict[str, Any]]):
        for adaccount in adaccounts:
            ads_task = cls.create(user, template, adaccount)
            ads_task.remote_create()

    @classmethod
    @transaction.atomic
    def create(cls, user: User, template: CampaignTemplate, adaccount: Dict[str, Any]):
        now = timezone.now()

        # TODO: Сделать нормально
        from api.v1.serializers.automation import CampaignTemplateSerializer

        campaign_data = CampaignTemplateSerializer(adaccount['campaign']).data

        adaccount_data = {
            'id': adaccount['adaccount'].id,
            'page': adaccount['page'].id,
        }
        if 'pixel' in adaccount:
            adaccount_data['pixel'] = adaccount['pixel']

        if adaccount.get('daily_budget'):
            adaccount_data['daily_budget'] = adaccount.get('daily_budget')
        elif adaccount.get('lifetime_budget'):
            adaccount_data['lifetime_budget'] = adaccount.get('lifetime_budget')

        if 'rules' in adaccount:
            adaccount_data['rules'] = [rule.id for rule in adaccount['rules']]

        ads_task = cls.objects.create(
            user=user,
            template=template,
            account_id=adaccount['adaccount'].account_id,
            adaccount=adaccount['adaccount'],
            created_at=now,
            adaccount_data=adaccount_data,
            campaign_data=campaign_data,
        )

        return ads_task

    @classmethod
    @transaction.atomic
    def update(cls, pk: int, **kwargs):
        ads_task = cls.objects.select_for_update().get(id=pk)
        for field_name, value in kwargs.items():
            setattr(ads_task, field_name, value)

        changed_data = ads_task.get_changed_data()
        if changed_data:
            ads_task.save()
            # Action.create(actor=None, action_datetime=now, verb='updated user', action_object=user,
            # data=changed_data)
        return ads_task

    @transaction.atomic
    def remote_create(self):
        from core.tasks.facebook import CreateAds

        # обрабатываем только в конце транзакции
        create_ads = CreateAds()
        transaction.on_commit(lambda: create_ads.delay(ads_task_id=self.id))


class FinAccount(LogChangedMixin):
    name = models.CharField(_('Name'), max_length=64)
    slug = models.SlugField(_('Slug'), max_length=64)
    fin_type = models.CharField(default='cross', max_length=12)
    description = models.CharField(_('Description'), max_length=256, null=True, blank=True)
    comment = models.CharField(_('Comment'), max_length=256, null=True, blank=True)

    data = encrypt(models.JSONField(encoder=DjangoJSONEncoder, blank=True, null=True))

    balance = models.DecimalField(_('Balance'), decimal_places=2, max_digits=10, default=0)
    currency = models.CharField(_('Currency'), default='USD', max_length=3)

    is_active = models.BooleanField(_('Is active'), default=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_finaccs')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    fieldtracker = FieldTracker()

    def __str__(self):
        return self.name

    @classmethod
    @transaction.atomic
    def create(
        cls,
        name: str,
        description: str,
        comment: str,
        currency: str,
        created_by: User,
        fin_type: str = 'cross',
        balance: Decimal = Decimal('0.00'),
        data: Dict[str, Any] = None,
    ):
        now = timezone.now()

        fin_account_data = {
            'name': name,
            'slug': slugify(name),
            'description': description,
            'comment': comment,
            'balance': balance,
            'currency': currency,
            'data': data,
            'fin_type': fin_type,
            'created_at': now,
            'created_by_id': created_by.id,
        }
        fin_account = cls.objects.create(**fin_account_data)

        Action.create(
            action_datetime=timezone.now(),
            actor=created_by,
            verb='Fin account created',
            action_object=fin_account,
            data=fin_account_data,
        )
        return fin_account

    @classmethod
    @transaction.atomic
    def update(cls, pk: int, updated_by: User, **kwargs):
        now = timezone.now()
        fin_account = cls.objects.select_for_update().get(id=pk)
        for field_name, value in kwargs.items():
            setattr(fin_account, field_name, value)

        changed_data = fin_account.get_changed_data()
        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            fin_account.save(update_fields=update_fields)

            Action.create(
                actor=updated_by,
                action_datetime=now,
                verb='Fin account changed',
                action_object=fin_account,
                data=changed_data,
            )
        return fin_account


class FinAccountTransaction(models.Model):
    account = models.ForeignKey(FinAccount, on_delete=models.PROTECT)
    amount = models.DecimalField(_('Amount'), decimal_places=2, max_digits=10, default=0)
    created_at = models.DateTimeField(default=timezone.now)


class FinCard(models.Model):
    external_id = models.PositiveIntegerField(_('Card id'), null=True, blank=True)  # Надо ли null?
    display_string = models.CharField(max_length=24, null=True, blank=True)

    balance = models.DecimalField(_('Balance'), decimal_places=2, max_digits=10, default=0)
    currency = models.CharField(_('Currency'), default='USD', max_length=3)

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_fincards')
    created_at = models.DateTimeField(default=timezone.now)


class FinCardTransaction(models.Model):
    account = models.ForeignKey(FinAccount, on_delete=models.PROTECT)
    card = models.ForeignKey(FinCard, on_delete=models.PROTECT)
    amount = models.DecimalField(_('Amount'), decimal_places=2, max_digits=10, default=0)
    description = models.CharField(_('Description'), max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
