import uuid

from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from model_utils import FieldTracker

from core.models.core import LogChangedMixin


class Contact(LogChangedMixin):
    GENDER_CHOICES = (
        (None, 'Unknown'),
        (0, 'Male'),
        (1, 'Female'),
    )
    email = models.EmailField("Email", null=True, blank=True)
    phone = models.CharField("Phone", max_length=32, null=True, blank=True)
    first_name = models.CharField('First Name', max_length=255, null=True, blank=True)
    last_name = models.CharField('Last name', max_length=255, null=True, blank=True)
    name = models.CharField('Name', max_length=255, null=True, blank=True)
    country = models.CharField('Country', max_length=2, null=True, blank=True)
    city = models.CharField('City', max_length=128, null=True, blank=True)
    zip = models.CharField('ZIP', max_length=128, null=True, blank=True)
    address = models.CharField('Address', max_length=255, null=True, blank=True)
    created_at = models.DateTimeField('Date added', default=timezone.now)
    offer = models.CharField(max_length=32, null=True, blank=True)
    network = models.CharField(max_length=32, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    referer = models.CharField(null=True, blank=True, max_length=4096)
    visit_id = models.UUIDField('Visit ID', db_index=True, default=uuid.uuid4, unique=True)
    gender = models.PositiveSmallIntegerField(choices=GENDER_CHOICES, null=True, blank=True)
    has_leads = models.BooleanField(default=False)
    fake_email = models.BooleanField(default=False)
    raw_data = models.JSONField(encoder=DjangoJSONEncoder, null=True, blank=True)
    postback_data = models.JSONField(encoder=DjangoJSONEncoder, null=True, blank=True)
    device_data = models.JSONField(encoder=DjangoJSONEncoder, null=True, blank=True)
    geo_data = models.JSONField(encoder=DjangoJSONEncoder, null=True, blank=True)
    answers = ArrayField(base_field=models.JSONField(), null=True, blank=True)

    fieldtracker = FieldTracker()

    def __str__(self):
        return self.full_name or f'{self.visit_id}'

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    @property
    def full_name(self):
        return self.get_full_name()

    @classmethod
    @transaction.atomic
    def create(cls, **kwargs):
        contact = cls.objects.create(**kwargs)
        return contact

    @classmethod
    @transaction.atomic
    def update(cls, pk: int, **kwargs):
        contact = cls.objects.select_for_update().get(pk=pk)

        for field_name, value in kwargs.items():
            setattr(contact, field_name, value)

        changed_data = contact.get_changed_data()

        update_fields = [x['field'] for x in changed_data]

        if changed_data:
            contact.save(update_fields=update_fields)
        return contact


# Это вообще от Маничата
class UserEmail(models.Model):
    user_id = models.BigIntegerField('User ID')
    page_id = models.BigIntegerField('Page ID')
    email = models.EmailField("Email", null=True, blank=True)
    phone = models.CharField("Phone", max_length=32, null=True, blank=True)
    first_name = models.CharField('First Name', max_length=255, null=True, blank=True)
    last_name = models.CharField('Last name', max_length=255, null=True, blank=True)
    name = models.CharField('Name', max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(_('Date added'), auto_now_add=True)

    def __str__(self):
        return self.name or self.user_id
