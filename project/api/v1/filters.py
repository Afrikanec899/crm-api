import re
from functools import reduce
from operator import or_

from django.db.models import Q
from django.utils import timezone

from django_filters import OrderingFilter
from django_filters import rest_framework as filters
from django_filters.constants import EMPTY_VALUES

from core.models import Contact, User
from core.models.core import (
    Account,
    AccountLog,
    AccountPayment,
    AdAccount,
    AdAccountCreditCard,
    AdAccountTransaction,
    AdsCreateTask,
    Campaign,
    CampaignTemplate,
    Country,
    FBPage,
    Leadgen,
    LeadgenLead,
    LinkGroup,
    Notification,
    PageCategory,
    Rule,
    ShortifyDomain,
    Tag,
    UserAccountDayStat,
    UserDayStat,
    UserKPI,
    UserRequest,
)


class CustomOrderingFilter(OrderingFilter):
    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs

        ordering = [self.get_ordering_value(param) for param in value]
        if 'status' in ordering:
            idx = ordering.index('status') + 1
            ordering[idx:idx] = ['status_changed_at']
        elif '-status' in ordering:
            idx = ordering.index('-status') + 1
            ordering[idx:idx] = ['-status_changed_at']

        return qs.order_by(*ordering)


class TagFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr='icontains')

    class Meta:
        model = Tag
        fields = ['name']


class CountryFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr='icontains')

    class Meta:
        model = Country
        fields = ['name', 'code']


class DomainFilter(filters.FilterSet):
    domain = filters.CharFilter(field_name="domain", lookup_expr='icontains')

    class Meta:
        model = ShortifyDomain
        fields = [
            'domain',
        ]


class PageCategoryFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr='icontains')

    class Meta:
        model = PageCategory
        fields = ['name', 'fb_id']


class CampaignFilter(filters.FilterSet):
    search = filters.CharFilter(method='search_filter')
    account = filters.NumberFilter(method='account_filter')

    def account_filter(self, queryset, name, value):
        if not value:
            return queryset

        connected_campaigns = (
            AdAccount.objects.filter(campaign__in=queryset)
            .exclude(Q(account_id=value) | Q(business__deleted_at__isnull=False))
            .values_list('campaign_id', flat=True)
        )
        return queryset.exclude(id__in=list(connected_campaigns))

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset

        query = Q(name__icontains=value)

        # if value.isdigit():
        #     query |= Q(id=value)
        return queryset.filter(query)

    class Meta:
        model = Campaign
        fields = ('search', 'account')


class AccountLogFilter(filters.FilterSet):
    class Meta:
        model = AccountLog
        fields = ['log_type', 'account', 'manager']


class AccountStatusLogFilter(filters.FilterSet):
    class Meta:
        model = AccountLog
        fields = ['account']


class AccountFilter(filters.FilterSet):
    status = filters.NumberFilter(field_name="status")
    search = filters.CharFilter(method='search_filter')
    manager = filters.NumberFilter(field_name='manager', method='manager_filter')
    team = filters.NumberFilter(field_name='team', method='team_filter')
    supplier = filters.NumberFilter(field_name='supplier', method='supplier_filter')
    show_banned = filters.BooleanFilter(field_name='show_banned', method='banned_filter')
    show_my_accounts = filters.BooleanFilter(field_name='show_my_accounts', method='owned_filter')

    ordering = CustomOrderingFilter(
        fields=(
            ('id', 'account'),
            ('status', 'status'),
            ('created_at', 'created'),
            ('supplier_id', 'supplier'),
            ('manager_id', 'manager'),
            ('fb_spends', 'spends'),
            ('total_funds', 'funds'),
            ('price', 'payments'),
        ),
    )

    def __init__(self, data, *args, **kwargs):

        if not data.get('show_banned'):
            data = data.copy()
            data['show_banned'] = False

        if not data.get('show_my_accounts'):
            data = data.copy()
            data['show_my_accounts'] = False

        super().__init__(data, *args, **kwargs)

    def banned_filter(self, queryset, name, value):
        if not value:
            return queryset.exclude(status=Account.BANNED)
        return queryset

    def owned_filter(self, queryset, name, value):
        if value:
            return queryset.filter(manager=self.request.user)
        return queryset

    def manager_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(manager__isnull=True)
        return queryset.filter(manager_id=value)

    def team_filter(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(manager__isnull=False, manager__team_id=value) | Q(supplier__isnull=False, supplier__team_id=value)
            )
        return queryset

    def supplier_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(supplier__isnull=True)
        return queryset.filter(supplier_id=value)

    def search_filter(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset

        is_exclude = False
        if value.startswith('-'):
            is_exclude = True
            value = value[1:]

        query = Q(login__icontains=value) | Q(tags__icontains=value) | Q(comment__icontains=value)

        if value.isdigit():
            query |= Q(id=value)

        if self.request.user.role in [User.FINANCIER, User.ADMIN]:
            query |= (
                Q(manager__username__icontains=value)
                | Q(password__icontains=value)
                | Q(card_number__icontains=value)
                | Q(financial_comment__icontains=value)
                | Q(comment__icontains=value)
            )

        if is_exclude:
            return queryset.exclude(query)

        return queryset.filter(query)

    class Meta:
        model = Account
        fields = ['status', 'manager', 'show_banned', 'show_my_accounts', 'search', 'supplier']


class NotificationFilter(filters.FilterSet):
    readed = filters.BooleanFilter(field_name='readed_at', lookup_expr='isnull', exclude=True)

    class Meta:
        model = Notification
        fields = ['readed']


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class UserStatFilter(filters.FilterSet):
    team = filters.NumberFilter(field_name="user__team_id", method='team_filter')

    def team_filter(self, queryset, name, value):
        return queryset.filter(user__team_id=value)

    class Meta:
        model = UserAccountDayStat
        fields = ['team']


class UserFilter(filters.FilterSet):
    id = NumberInFilter(field_name='id', lookup_expr='in')
    role = NumberInFilter(field_name='role', lookup_expr='in')
    team = NumberInFilter(field_name='team_id', lookup_expr='in')
    search = filters.CharFilter(field_name="name", method='search_filter')
    show_inactive = filters.BooleanFilter(field_name='is_active', method='inactive_filter')

    def __init__(self, data, *args, **kwargs):
        if not data.get('show_inactive'):
            data = data.copy()
            data['show_inactive'] = False
        super().__init__(data, *args, **kwargs)

    def inactive_filter(self, queryset, name, value):
        if value:
            return queryset
        return queryset.filter(is_active=True)

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset

        return queryset.filter(
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(username__icontains=value)
            | Q(email__icontains=value)
        )

    class Meta:
        model = User
        fields = ['id', 'role', 'team', 'search']


class StatDateFilter(filters.FilterSet):
    date_from = filters.CharFilter(field_name="date", lookup_expr='gte')
    date_to = filters.CharFilter(field_name="date", lookup_expr='lte')
    manager = filters.NumberFilter(field_name='manager', method='user_filter')
    show_banned = filters.BooleanFilter(field_name='show_banned', method='banned_filter')
    show_fired = filters.BooleanFilter(field_name='show_fired', method='fired_filter')
    team = filters.NumberFilter(field_name="team", method='team_filter')

    def __init__(self, data, *args, **kwargs):
        data = data.copy()
        if not data.get('show_banned'):
            data['show_banned'] = True

        if not data.get('show_fired'):
            data['show_fired'] = True
        super().__init__(data, *args, **kwargs)

    def banned_filter(self, queryset, name, value):
        if not value:
            return queryset.exclude(account__status=Account.BANNED)
        return queryset

    def fired_filter(self, queryset, name, value):
        if not value:
            return queryset.exclude(user__is_active=False)
        return queryset

    def team_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__team_id__isnull=True)
        return queryset.filter(user__team_id=value)

    def user_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    class Meta:
        model = UserAccountDayStat
        fields = ['date_from', 'date_to', 'manager', 'account']


class StatDateFilter2(filters.FilterSet):
    date_from = filters.CharFilter(field_name="date", lookup_expr='gte')
    date_to = filters.CharFilter(field_name="date", lookup_expr='lte')
    manager = filters.NumberFilter(field_name='manager', method='user_filter')
    team = filters.NumberFilter(field_name="team", method='team_filter')

    def team_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__team_id__isnull=True)
        return queryset.filter(user__team_id=value)

    def user_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    class Meta:
        model = UserDayStat
        fields = ['date_from', 'date_to', 'manager', 'account']


#
# class AdAccountStatDateFilter(StatDateFilter):
#     class Meta(StatDateFilter.Meta):
#         model = UserAdAccountDayStatNew
#         fields = [
#             'date_from',
#             'date_to',
#             'manager',
#         ]


class FlowStatDateFilter(filters.FilterSet):
    date_from = filters.CharFilter(field_name="date", lookup_expr='gte')
    date_to = filters.CharFilter(field_name="date", lookup_expr='lte')
    manager = filters.NumberFilter(field_name='manager', method='user_filter')

    def user_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)


class RequestsFilter(filters.FilterSet):
    manager = filters.NumberFilter(field_name='user_id')
    search = filters.CharFilter(field_name='search', method='search_filter')
    status = filters.NumberFilter(field_name='status', method='status_filter')
    date_from = filters.DateFilter(field_name="updated_at__date", lookup_expr='gte')
    date_to = filters.DateFilter(field_name="updated_at__date", lookup_expr='lte')

    def status_filter(self, queryset, name, value):
        if value == 100:
            return queryset.filter(status__in=[UserRequest.PROCESSING, UserRequest.WAITING])
        return queryset.filter(status=value)

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(request_data__comment__icontains=value)
            | Q(request_data__account_id__icontains=value)
            | Q(request_data__status_comment__icontains=value)
        )

    class Meta:
        model = UserRequest
        fields = ['status', 'search', 'manager', 'processed_by']


class KPIFilter(filters.FilterSet):
    is_current = filters.BooleanFilter(field_name='is_current', method='current_filter')
    user = filters.NumberFilter(field_name='user', method='user_filter')

    def user_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    def current_filter(self, queryset, name, value):
        if value:
            today = timezone.now().date()
            return queryset.filter(start_at__lte=today, end_at__gte=today)
        return queryset

    class Meta:
        model = UserKPI
        fields = ('user',)


class FBPageFilter(filters.FilterSet):
    class Meta:
        model = FBPage
        fields = ('account', 'page_id')


class AdAccountFilter(filters.FilterSet):
    card = filters.NumberFilter(field_name='card', method='card_filter')
    search = filters.CharFilter(field_name='search', method='search_filter')

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset

        return queryset.filter(Q(name__icontains=value) | Q(business__name__icontains=value))

    def card_filter(self, queryset, name, value):
        if value:
            adaccount_cards = AdAccountCreditCard.objects.filter(card_id=value)
            if adaccount_cards.exists():
                adaccount_ids = adaccount_cards.values_list('adaccount_id', flat=True)
                queryset = queryset.filter(id__in=list(adaccount_ids))
                return queryset
            else:
                return queryset.none()
        return queryset

    class Meta:
        model = AdAccount
        fields = ('account', 'status', 'business', 'card', 'id')


class CreditCardFilter(filters.FilterSet):
    search = filters.CharFilter(field_name='search', method='search_filter')
    show_inactive = filters.BooleanFilter(field_name='is_active', method='inactive_filter')

    def __init__(self, data, *args, **kwargs):
        if not data.get('show_inactive'):
            data = data.copy()
            data['show_inactive'] = False
        super().__init__(data, *args, **kwargs)

    def inactive_filter(self, queryset, name, value):
        if value:
            return queryset
        return queryset.filter(Q(card__is_active=True) | Q(card__isnull=True))

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset

        return queryset.filter(
            Q(card__number__icontains=value)
            | Q(card__comment__icontains=value)
            | Q(card__display_string__icontains=value)
        )

    class Meta:
        model = AdAccountCreditCard
        fields = ('search', 'show_inactive')


class TransactionFilter(filters.FilterSet):
    search = filters.CharFilter(field_name='search', method='search_filter')
    date_from = filters.CharFilter(field_name="billed_at__date", lookup_expr='gte')
    date_to = filters.CharFilter(field_name="billed_at__date", lookup_expr='lte')
    has_card = filters.BooleanFilter(field_name='has_card', method='has_card_filter')
    card = filters.NumberFilter(field_name='card', method='card_filter')

    def card_filter(self, queryset, name, value):
        if value:
            return queryset.filter(card_id=value)
        return queryset

    def has_card_filter(self, queryset, name, value):
        if value is not None:
            if value is True:
                return queryset.filter(card__number__isnull=False)
            else:
                return queryset.filter(card__number__isnull=True)
        return queryset

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset

        return queryset.filter(name__icontains=value)

    class Meta:
        model = AdAccountTransaction
        fields = (
            'search',
            'date_from',
            'date_to',
            'adaccount_id',
            'card',
            'adaccount_card',
            'charge_type',
            'has_card',
        )


class RuleFilter(filters.FilterSet):
    search = filters.CharFilter(field_name='search', method='search_filter')
    manager = filters.NumberFilter(field_name='manager', method='manager_filter')

    def manager_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset

        return queryset.filter(name__icontains=value)

    class Meta:
        model = Rule
        fields = ('search', 'manager')


class TemplateFilter(filters.FilterSet):
    search = filters.CharFilter(field_name='search', method='search_filter')
    manager = filters.NumberFilter(field_name='manager', method='manager_filter')

    def manager_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset

        return queryset.filter(name__icontains=value)

    class Meta:
        model = CampaignTemplate
        fields = ('search', 'manager')


class AdsCreateTaskLogFilter(filters.FilterSet):
    manager = filters.NumberFilter(field_name='manager', method='manager_filter')

    def manager_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    class Meta:
        model = AdsCreateTask
        fields = ('manager',)


class AccountPaymentFilter(filters.FilterSet):
    date_from = filters.CharFilter(field_name="date", lookup_expr='gte')
    date_to = filters.CharFilter(field_name="date", lookup_expr='lte')

    class Meta:
        model = AccountPayment
        fields = (
            'date_to',
            'date_from',
        )


class AccountPaymentDataFilter(filters.FilterSet):
    class Meta:
        model = Account
        fields = ('supplier',)


class ContactFilter(filters.FilterSet):
    date_from = filters.CharFilter(field_name="created_at__date", lookup_expr='gte')
    date_to = filters.CharFilter(field_name="created_at__date", lookup_expr='lte')
    country = filters.CharFilter(field_name='country', lookup_expr='icontains')
    search = filters.CharFilter(field_name='search', method='search_filter')

    def search_filter(self, queryset, name, value):
        value = re.sub(r'\W+', ' ', value).strip()
        if not value:
            return queryset

        return queryset.filter(offer__icontains=value)

    class Meta:
        model = Contact
        fields = ('date_to', 'date_from', 'country', 'search')


class LeadgenFilter(filters.FilterSet):
    manager = filters.NumberFilter(field_name='manager', method='manager_filter')

    def manager_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    class Meta:
        model = Leadgen
        fields = ('manager',)


class LeadgenBroadcastFilter(filters.FilterSet):
    manager = filters.NumberFilter(field_name='manager', method='manager_filter')

    def manager_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    class Meta:
        model = LinkGroup
        fields = ('manager',)


class LeadgenLeadFilter(filters.FilterSet):
    date_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr='gte')
    date_to = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr='lte')
    country = filters.CharFilter(field_name='country', method='country_filter')
    search = filters.CharFilter(field_name='search', method='search_filter')
    manager = NumberInFilter(field_name='manager', method='manager_filter')
    is_new = filters.BooleanFilter(field_name='is_new', method='isnew_filter')

    def country_filter(self, queryset, name, value):
        if value:
            return queryset.filter(country_code__icontains=value)
        return queryset

    def isnew_filter(self, queryset, name, value):
        if value:
            return queryset.filter(exported_at__isnull=True)
        return queryset

    def manager_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id__in=value)

    def search_filter(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        values = list(filter(lambda x: x.strip(), value.split(',')))
        return queryset.filter(reduce(or_, (Q(offer__icontains=search.strip()) for search in values)))

    class Meta:
        model = LeadgenLead
        fields = ('date_to', 'date_from', 'country', 'search', 'account', 'manager')


class LeadgenLeadStatsFilter(filters.FilterSet):
    date_from = filters.CharFilter(field_name="created_at__date", lookup_expr='gte')
    date_to = filters.CharFilter(field_name="created_at__date", lookup_expr='lte')
    manager = filters.NumberFilter(field_name='manager', method='user_filter')

    def user_filter(self, queryset, name, value):
        if value == 0:
            return queryset.filter(user__isnull=True)
        return queryset.filter(user_id=value)

    class Meta:
        model = LeadgenLead
        fields = (
            'manager',
            'date_to',
            'date_from',
        )
