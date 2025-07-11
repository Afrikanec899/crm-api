import csv
import logging
from typing import Optional

from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.db.models import JSONField, Model, Q, QuerySet
from django.db.models.fields import TextField
from django.forms.models import BaseInlineFormSet
from django.forms.widgets import Textarea
from django.http import HttpRequest, StreamingHttpResponse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from django_json_widget.widgets import JSONEditorWidget
from fsm_admin.mixins import FSMTransitionMixin
from unidecode import unidecode

from core.models import ArrayField, User
from core.models.contacts import Contact, UserEmail
from core.models.core import Account  # UserAdAccountDayStatNew,
from core.models.core import (
    AccountActivityLog,
    AccountLog,
    AccountPayment,
    Action,
    Ad,
    AdAccount,
    AdAccountCreditCard,
    AdAccountDayStat,
    AdAccountLog,
    AdAccountTransaction,
    AdsCreateTask,
    BusinessManager,
    BusinessManagerLog,
    BusinessShareUrl,
    Campaign,
    CampaignDayStat,
    CampaignLog,
    CampaignTemplate,
    Card,
    Config,
    Country,
    Domain,
    FBPage,
    FieldsSetting,
    FinAccount,
    Flow,
    FlowDayStat,
    Leadgen,
    LeadgenLead,
    LeadgenLeadConversion,
    Link,
    LinkGroup,
    Notification,
    NotificationSubscription,
    PageCategory,
    PageLeadgen,
    ProcessCSVTask,
    Rule,
    ShortifyDomain,
    Tag,
    Team,
    UploadedImage,
    UploadedVideo,
    UserAccountDayStat,
    UserAdAccountDayStat,
    UserCampaignDayStat,
    UserDayStat,
    UserKPI,
    UserRequest,
    UserRequestLog,
)
from core.pagination import LargeTablePaginator
from core.tasks import (
    clear_account_stats_task,
    load_fb_leads,
    reload_account_fb_stats_task,
    reload_tracker_campaign_stats,
    update_tracker_costs,
)
from core.tasks.links import fill_shortify_cache_task

admin.site.unregister(Group)
logger = logging.getLogger(__name__)


class PseudoBuffer:
    """An object that implements just the write method of the file-like
    interface.
    """

    def write(self, value):
        """Write the value by returning it, instead of storing in a buffer."""
        return value


class AccountStatusLogInline(admin.TabularInline):
    model = AccountLog
    fields = ('start_at', 'end_at', 'status', 'changed_by')
    can_delete = False
    verbose_name = 'Status log'
    verbose_name_plural = 'Status log'

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return (
            super(AccountStatusLogInline, self)
            .get_queryset(request)
            .filter(log_type=AccountLog.STATUS)
            .prefetch_related('changed_by')
            .order_by('-start_at')
        )

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class AccountManagerLogInline(admin.TabularInline):
    model = AccountLog
    fields = ('start_at', 'end_at', 'manager', 'changed_by')
    can_delete = False
    verbose_name = 'Manager log'
    verbose_name_plural = 'Manager log'

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return (
            super(AccountManagerLogInline, self)
            .get_queryset(request)
            .filter(log_type=AccountLog.MANAGER)
            .prefetch_related('changed_by')
            .prefetch_related('manager')
            .order_by('-start_at')
        )

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class AdAccountCardInline(admin.TabularInline):
    model = AdAccountCreditCard
    fields = (
        'card',
        'credential_id',
        'created_at',
    )
    can_delete = False
    verbose_name = 'Card'
    verbose_name_plural = 'Cards'
    ordering = ('-created_at',)

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class AdAccountStatusLogInline(admin.TabularInline):
    model = AdAccountLog
    fields = (
        'start_at',
        'end_at',
        'status',
    )
    can_delete = False
    verbose_name = 'Status log'
    verbose_name_plural = 'Status log'
    ordering = ('-start_at',)

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class LimitModelFormset(BaseInlineFormSet):
    """ Base Inline formset to limit inline Model query results. """

    def __init__(self, *args, **kwargs):
        super(LimitModelFormset, self).__init__(*args, **kwargs)
        _kwargs = {self.fk.name: kwargs['instance']}
        self.queryset = kwargs['queryset'].filter(**_kwargs).order_by('-id')[:20]


class CampaignStatusLogInline(admin.TabularInline):
    model = CampaignLog
    formset = LimitModelFormset
    fields = ('start_at', 'end_at', 'status', 'changed_by')
    can_delete = False
    verbose_name = 'Status log'
    verbose_name_plural = 'Status log'

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        qs = (
            super(CampaignStatusLogInline, self)
            .get_queryset(request)
            .filter(log_type=CampaignLog.STATUS)
            .prefetch_related('changed_by')
            .order_by('-start_at')
        )
        return qs

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = CampaignLog) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class CampaignManagerLogInline(admin.TabularInline):
    model = CampaignLog
    formset = LimitModelFormset
    fields = ('start_at', 'end_at', 'manager', 'changed_by')
    can_delete = False
    verbose_name = 'Manager log'
    verbose_name_plural = 'Manager log'

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        qs = (
            super(CampaignManagerLogInline, self)
            .get_queryset(request)
            .filter(log_type=CampaignLog.MANAGER)
            .prefetch_related('changed_by')
            .prefetch_related('manager')
            .order_by('-start_at')
        )
        return qs

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = CampaignLog) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class ShareUrlInline(admin.TabularInline):
    model = BusinessShareUrl
    can_delete = False
    verbose_name = 'Share url'
    verbose_name_plural = 'Share urls'

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class BusinessManagerLogInline(admin.TabularInline):
    model = BusinessManagerLog
    formset = LimitModelFormset
    fields = (
        'account',
        'start_at',
        'end_at',
    )
    can_delete = False
    verbose_name = 'BM log'
    verbose_name_plural = 'BM log'

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class AccountAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ['status']
    list_filter = ('status', 'manager', 'created_by', 'status', 'supplier')
    search_fields = ('id', 'login', 'comment', 'mla_profile_id')
    readonly_fields = ('status',)
    inlines = (AccountStatusLogInline, AccountManagerLogInline)
    list_display = (
        'id',
        'country_code',
        'status',
        'manager',
        'comment',
        'created_by',
        'created_at',
        'supplier',
        'total_spends',
        'age',
        'paid_till',
    )
    list_editable = ('total_spends', 'paid_till')
    date_hierarchy = 'created_at'
    actions = ['reload_fb_stats', 'clear_account_stats', 'reload_tracker_stats', 'update_full_costs']
    actions_on_bottom = True
    actions_on_top = True

    def reload_tracker_stats(modeladmin, request, queryset):
        for account in queryset:
            days = (timezone.now() - account.created_at).days
            reload_tracker_campaign_stats.delay(account.id, days)
        modeladmin.message_user(request, "Tracker Stats Reloading!", level=messages.SUCCESS)

    reload_tracker_stats.short_description = "Reload Tracker Stats"

    def update_full_costs(modeladmin, request, queryset):
        for account in queryset:
            days = (timezone.now() - account.created_at).days
            update_tracker_costs.delay(account.id, days)
        modeladmin.message_user(request, "Tracker Costs Will update soon!", level=messages.SUCCESS)

    update_full_costs.short_description = "Update Tracker Costs"

    def reload_fb_stats(modeladmin, request, queryset):
        for account in queryset:
            days = (timezone.now() - account.created_at).days
            reload_account_fb_stats_task.delay(account.id, days)
        modeladmin.message_user(request, "FB Stats Reloading!", level=messages.SUCCESS)

    reload_fb_stats.short_description = "Reload FB Stats"

    def clear_account_stats(modeladmin, request, queryset):
        for account in queryset:
            clear_account_stats_task.delay(account.id)
        modeladmin.message_user(request, "Account Stats Clearing!", level=messages.SUCCESS)

    clear_account_stats.short_description = "Clear Account Stats"

    def get_queryset(self, request):
        return (
            super(AccountAdmin, self).get_queryset(request).prefetch_related('manager').prefetch_related('created_by')
        )


class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'sender',
        'recipient',
        'category',
        'level',
        'created_at',
        'sended_at',
        'sended_email_at',
        'sended_telegram_at',
        'readed_at',
    )
    readonly_fields = ('created_at', 'readed_at')
    list_filter = ('recipient', 'sender', 'category', 'level')
    date_hierarchy = 'created_at'
    formfield_overrides = {JSONField: {'widget': JSONEditorWidget}}

    def get_queryset(self, request):
        return (
            super(NotificationAdmin, self)
            .get_queryset(request)
            .prefetch_related('sender')
            .prefetch_related('recipient')
        )


class MyUserAdmin(UserAdmin):
    list_display = (
        'id',
        'telegram_id',
        'username',
        'email',
        'role',
        'team',
        'mla_group_id',
        'is_active',
        'is_superuser',
    )
    list_filter = ('role', 'team', 'is_active')
    list_editable = ('role', 'team', 'is_active', 'mla_group_id')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email', 'team')}),
        (_('Telegram info'), {'fields': ('photo_url', 'telegram_id')}),
        (_('Tracker info'), {'fields': ('tracker_type', 'tracker_login', 'tracker_password')}),
        (_('Proxy info'), {'fields': ('proxy_host', 'proxy_port', 'proxy_login', 'proxy_password')}),
        (_('MLA'), {'fields': ('mla_login', 'mla_group_id')}),
        (_('Permissions'), {'fields': ('role', 'is_active', 'is_staff', 'is_superuser')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )


class UserEmailAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'phone', 'page_id', 'user_id')
    date_hierarchy = 'created_at'
    actions = ['export_action']

    def export_action(modeladmin, request, queryset):
        def iter_write(items):
            pseudo_buffer = PseudoBuffer()
            writer = csv.writer(pseudo_buffer, delimiter=',')
            yield writer.writerow(  # type: ignore
                ['first_name', 'last_name', 'email']
            )
            for item in items:
                yield writer.writerow([item.first_name, item.last_name, item.email])  # type: ignore

        response = StreamingHttpResponse(iter_write(queryset), content_type="text/csv")
        response['Content-Disposition'] = f'attachment; filename="dating.csv"'
        return response

    export_action.short_description = "Export emails to CSV"


class AdAccountAdmin(admin.ModelAdmin):
    list_display = (
        'account',
        'manager',
        'adaccount_id',
        'name',
        'business',
        'campaign',
        'created_at',
        'status',
        'disable_reason',
        'payment_cycle',
        'amount_spent',
        'limit',
        'balance',
        'timezone_name',
        'currency',
        'deleted_at',
        'bills_load_at',
    )
    inlines = (AdAccountStatusLogInline, AdAccountCardInline)
    raw_id_fields = ('campaign', 'business', 'account')
    list_filter = ('account__manager__is_active', 'account__manager', 'status', 'disable_reason', 'currency')
    search_fields = ('pixels', 'name', 'business__name', 'campaign__name', 'adaccount_id')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super(AdAccountAdmin, self).get_queryset(request).prefetch_related('account')


class AdAccountTransactionAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super(AdAccountTransactionAdmin, self).get_queryset(request).prefetch_related('adaccount')

    list_display = (
        'adaccount',
        'card',
        'transaction_id',
        'amount',
        'currency',
        'start_at',
        'end_at',
        'billed_at',
        'created_at',
        'reason',
        'charge_type',
        'product_type',
        # 'payment_option',
        # 'status',
        # 'tracking_id',
        'transaction_type',
        # 'vat_invoice_id',
    )
    list_filter = ('currency', 'charge_type', 'product_type', 'transaction_type')
    search_fields = ('transaction_id', 'vat_invoice_id', 'tracking_id')
    raw_id_fields = ('adaccount', 'card', 'adaccount_card')
    date_hierarchy = 'billed_at'


class AdAccountDayStatAdmin(admin.ModelAdmin):
    list_display = ('account', 'adaccount', 'date', 'spend')
    raw_id_fields = (
        'account',
        'adaccount',
    )
    list_filter = ('account__manager', 'account__status')
    search_fields = ('adaccount__name',)
    date_hierarchy = 'date'


class AccountDayStatAdmin(admin.ModelAdmin):
    list_display = ('account', 'date', 'spend', 'visits', 'leads', 'revenue', 'profit', 'cost', 'clicks')
    list_filter = ('account__manager',)
    search_fields = ('account_id',)
    date_hierarchy = 'date'


class AdAccountStatAdmin(admin.ModelAdmin):
    list_display = ('user', 'account', 'adaccount', 'created_at', 'spend_diff')
    list_filter = ('user__is_active', 'user')
    date_hierarchy = 'created_at'


class CampaignDayStatAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'date', 'visits', 'leads', 'clicks', 'revenue', 'cost', 'profit')
    list_filter = ('campaign__user',)
    search_fields = ('campaign__name',)
    date_hierarchy = 'date'


class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'campaign_id', 'symbol', 'user', 'status', 'tracking_url', 'country_code')
    list_filter = ('status', 'country_code', 'user')
    inlines = (CampaignStatusLogInline, CampaignManagerLogInline)

    search_fields = (
        'name',
        'symbol',
    )


class FlowAdmin(admin.ModelAdmin):
    list_display = ('flow_name', 'flow_id', 'status')
    list_filter = ('status',)


class DomainAdmin(admin.ModelAdmin):
    list_display = ('name', 'domain_id', 'deleted_at', 'is_banned', 'is_internal')
    list_filter = ('is_banned', 'is_internal')
    list_editable = ('is_internal',)
    search_fields = ('name',)


class ShortifyDomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'is_public', 'is_banned', 'sort')
    list_editable = ('is_public', 'is_banned', 'sort')
    list_filter = ('is_public', 'is_banned')
    search_fields = ('domain',)


class CountryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_public', 'sort')
    list_editable = ('is_public', 'sort')
    list_filter = ('is_public',)


class PageCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'fb_id', 'is_public', 'sort')
    search_fields = ('name',)
    list_editable = ('is_public', 'sort')
    list_filter = ('is_public',)


class FlowDayStatAdmin(admin.ModelAdmin):
    list_display = ('flow', 'date', 'visits', 'leads', 'clicks', 'revenue', 'cost', 'profit', 'ctr', 'cr', 'epc')
    date_hierarchy = 'date'


class AdAdmin(admin.ModelAdmin):
    list_display = (
        'adaccount',
        'page',
        'name',
        'ad_id',
        'status',
        'effective_status',
        'creative_id',
        'story_id',
        'ad_url',
        'total_comments',
        'ad_review_feedback',
        'created_at',
        'disable_check',
    )
    list_filter = ('status', 'effective_status', 'disable_check')
    search_fields = ('page__name', 'name', 'creative_id', 'story_id', 'adaccount__name', 'ad_id', 'ad_url')
    date_hierarchy = 'created_at'


class FBPageAdmin(admin.ModelAdmin):
    list_display = ('name', 'account', 'page_id', 'is_published', 'deleted_at', 'created_at')
    raw_id_fields = ('account',)
    search_fields = ('name', 'page_id', 'account__id')
    list_filter = ('is_published',)
    date_hierarchy = 'created_at'


class ActionAdmin(admin.ModelAdmin):
    show_full_result_count = False
    paginator = LargeTablePaginator
    list_display = ('verb', 'actor_id', 'action_datetime', 'action_object_repr', 'target_object_repr')
    # list_filter = ('actor', 'verb')
    raw_id_fields = ('target_object_content_type', 'action_object_content_type')
    # date_hierarchy = 'action_datetime'
    search_fields = ('action_object_repr', 'target_object_repr', 'verb')

    def has_delete_permission(self, request: HttpRequest, obj: Optional[Model] = ...) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Optional[Model] = CampaignLog) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False

    # def get_queryset(self, request):
    #     return super(ActionAdmin, self).get_queryset(request).prefetch_related('actor')


class ConfigAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'typed_value', 'value_type', 'updated', 'is_active')
    list_filter = ('is_active', 'value_type')
    list_editable = ('is_active',)


class UserRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'request_type', 'comment', 'status', 'processed_by', 'created_at', 'updated_at')
    list_filter = ('request_type', 'status', 'processed_by', 'user')
    search_fields = ('comment',)
    formfield_overrides = {JSONField: {'widget': JSONEditorWidget}}
    date_hierarchy = 'created_at'


class FieldsSettingAdmin(admin.ModelAdmin):
    list_display = ('user', 'slug')


class AccountLogAdmin(admin.ModelAdmin):
    list_display = ('account', 'status', 'manager', 'card_number', 'start_at', 'end_at', 'log_type', 'changed_by')
    list_filter = ('status', 'log_type', 'manager')
    date_hierarchy = 'start_at'

    def has_delete_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class BusinessManagerLogAdmin(admin.ModelAdmin):
    list_display = ('business', 'account', 'manager', 'start_at', 'end_at', 'log_type', 'changed_by')
    list_filter = ('log_type', 'manager')
    date_hierarchy = 'start_at'

    def has_delete_permission(self, request: HttpRequest, obj: Optional[Model] = AccountLog) -> bool:
        return False


class CampaignLogAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'status', 'manager', 'start_at', 'end_at', 'log_type', 'changed_by')
    list_filter = ('status', 'log_type', 'manager')
    date_hierarchy = 'start_at'

    def has_delete_permission(self, request: HttpRequest, obj: Optional[Model] = CampaignLog) -> bool:
        return False


class AdAccountLogAdmin(admin.ModelAdmin):
    list_display = ('adaccount', 'status', 'manager', 'start_at', 'end_at', 'log_type', 'changed_by')
    list_filter = ('status', 'log_type', 'manager')
    date_hierarchy = 'start_at'
    #
    # def has_delete_permission(self, request: HttpRequest, obj: Optional[Model] = AdAccountLog) -> bool:
    #     return False


class UserRequestLogAdmin(admin.ModelAdmin):
    list_display = ('user_request', 'status', 'start_at', 'end_at')
    list_filter = ('status',)
    date_hierarchy = 'start_at'


class AccountActivityLogAdmin(admin.ModelAdmin):
    list_display = ('account', 'user', 'start_at', 'end_at', 'duration')
    list_filter = ('user',)
    date_hierarchy = 'start_at'


class DeletedFilter(SimpleListFilter):
    title = 'Removed'
    parameter_name = 'deleted'

    def lookups(self, request, model_admin):
        return (
            ('removed', _('removed')),
            ('not_removed', _('not removed')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'removed':
            return queryset.filter(deleted_at__isnull=False)
        elif self.value() == 'not_removed':
            return queryset.filter(deleted_at__isnull=True)
        else:
            return queryset


class HasAnswersFilter(SimpleListFilter):
    title = 'Has Answers'
    parameter_name = 'has_answers'

    def lookups(self, request, model_admin):
        return (
            ('true', _('Has Answers')),
            ('false', _('Without answers')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'true':
            return queryset.filter(answers__isnull=False)
        elif self.value() == 'false':
            return queryset.filter(Q(answers__isnull=True) | Q(answers='{}'))
        else:
            return queryset


class HasEmailFilter(SimpleListFilter):
    title = 'Has email'
    parameter_name = 'has_email'

    def lookups(self, request, model_admin):
        return (
            ('true', _('Has email')),
            ('false', _('Without email')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'true':
            return queryset.filter(email__isnull=False)
        elif self.value() == 'false':
            return queryset.filter(Q(email__isnull=True) | Q(email=''))
        else:
            return queryset


class BusinessManagerAdmin(admin.ModelAdmin):
    list_display = ('account', 'name', 'business_id', 'created_at', 'can_create_ad_account', 'deleted_at')
    list_filter = (DeletedFilter, 'can_create_ad_account')
    search_fields = ('name',)
    date_hierarchy = 'created_at'
    inlines = (ShareUrlInline, BusinessManagerLogInline)


class BusinessShareUrlAdmin(admin.ModelAdmin):
    list_display = (
        'business',
        'url',
        'email',
        'status',
        'role',
        'created_at',
        'expire_at',
    )
    date_hierarchy = 'created_at'


class RuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'user', 'created_at')
    list_filter = ('user',)
    search_fields = ('name',)
    date_hierarchy = 'created_at'


class LeadgenAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'user', 'created_at')
    list_filter = ('user',)
    search_fields = ('name',)
    date_hierarchy = 'created_at'
    formfield_overrides = {JSONField: {'widget': JSONEditorWidget}}


class PageLeadgenAdmin(admin.ModelAdmin):
    list_display = ('id', 'leadgen', 'page', 'created_at', 'last_load')
    raw_id_fields = ('page', 'leadgen')
    list_filter = ('leadgen__user',)
    search_fields = ('leadgen__name', 'page__name')
    actions = ['reload_leads']

    def reload_leads(modeladmin, request, queryset):
        for page_leadgen in queryset:
            load_fb_leads.delay(page_leadgen.id, True)
            modeladmin.message_user(
                request, f"Downloading leads from Page {page_leadgen.page.name} started!", level=messages.SUCCESS
            )

    reload_leads.short_description = "Download all leads from FB"


class LinkGroupAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'user',
        'status',
        'created_at',
        'total_links',
        'total_clicks',
        'click_rate',
        'clicked_links',
        'csv',
    )
    list_filter = ('user', 'status')
    date_hierarchy = 'created_at'
    actions = ['fill_shortify_cache', 'export_not_clicked']

    def export_not_clicked(modeladmin, request, queryset):
        def iter_write(items):
            pseudo_buffer = PseudoBuffer()
            writer = csv.writer(pseudo_buffer, delimiter=',')
            writer.writerow(['name', 'email', 'phone', 'url'])

            for item in items:
                cleared_name = unidecode(item.leadgen_lead.full_name)
                yield writer.writerow(
                    [cleared_name, item.leadgen_lead.email, item.leadgen_lead.phone, item.short_url,]
                )

        broadcast_ids = queryset.values_list('id', flat=True)
        links = Link.objects.filter(group_id__in=list(broadcast_ids), clicks=0)
        response = StreamingHttpResponse(iter_write(links), content_type="text/csv")
        response['Content-Disposition'] = f'attachment; filename="not_clicked-{timezone.now().date()}.csv"'
        return response

    export_not_clicked.short_description = "Export not clicked to CSV"

    def fill_shortify_cache(modeladmin, request, queryset):
        for group in queryset:
            fill_shortify_cache_task.delay(group.id)
            modeladmin.message_user(
                request, f"Filling Cache for Broadcast {group.name} Started!", level=messages.SUCCESS
            )

    fill_shortify_cache.short_description = "Fill Shortify Cache data"


class LinkAdmin(admin.ModelAdmin):
    paginator = LargeTablePaginator
    list_display = ('key', 'url', 'user', 'group', 'leadgen_lead_id', 'clicks', 'created_at')
    raw_id_fields = ('group', 'leadgen_lead')
    list_filter = ('user',)
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super(LinkAdmin, self).get_queryset(request).prefetch_related('group')


class LeadgenLeadAdmin(admin.ModelAdmin):
    list_display = (
        'lead_id',
        'page',
        'account_id',
        'leadgen',
        'user',
        'leadform_id',
        'visit_id',
        'name',
        'first_name',
        'last_name',
        'gender',
        'phone',
        'email',
        'country',
        'created_at',
        'offer',
        'network',
    )
    list_filter = (
        'country',
        'offer',
        'gender',
        'network',
    )
    raw_id_fields = ('account', 'page', 'leadgen')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'uuid')
    search_fields = ('phone', 'uuid', 'name')


class LeadgenLeadConversionAdmin(admin.ModelAdmin):
    list_display = (
        'lead_id',
        'campaign',
        'user',
        'payout',
        'offer_name',
        'device_brand',
        'country',
        'language',
        'city',
        'ip',
        'isp',
        'created_at',
    )
    list_filter = (
        'offer_name',
        'user',
        'country',
    )
    raw_id_fields = ('lead', 'campaign')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    actions = ['export_action']

    def export_action(modeladmin, request, queryset):
        def iter_write(items):
            pseudo_buffer = PseudoBuffer()
            writer = csv.writer(pseudo_buffer, delimiter=',')
            yield writer.writerow(  # type: ignore
                ['name', 'email', 'phone', 'country', 'city']
            )
            for item in items:
                cleared_name = unidecode(item.lead.full_name)

                yield writer.writerow(
                    [cleared_name, item.lead.email, item.lead.phone, item.country, item.city,]
                )

        response = StreamingHttpResponse(iter_write(queryset), content_type="text/csv")
        response['Content-Disposition'] = f'attachment; filename="conversions-{timezone.now().date()}.csv"'
        return response

    export_action.short_description = "Export to CSV"


class ContactAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'visit_id',
        'full_name',
        'first_name',
        'last_name',
        'gender',
        'phone',
        'email',
        'country',
        'created_at',
        'offer',
        'has_leads',
        'fake_email',
        'network',
    )
    list_filter = ('country', 'offer', 'gender', 'network', 'has_leads', HasAnswersFilter, HasEmailFilter)
    search_fields = ('visit_id', 'first_name', 'last_name', 'phone', 'email')
    date_hierarchy = 'created_at'
    actions = ['export_action']
    formfield_overrides = {JSONField: {'widget': JSONEditorWidget}, ArrayField: {'widget': Textarea}}

    def export_action(modeladmin, request, queryset):
        def iter_write(items):
            pseudo_buffer = PseudoBuffer()
            writer = csv.writer(pseudo_buffer, delimiter=',', quoting=csv.QUOTE_ALL)
            yield writer.writerow(  # type: ignore
                ['first_name', 'last_name', 'phone', 'email', 'zip', 'city', 'country', 'address', 'created_at']
            )
            for item in items:
                yield writer.writerow(
                    [
                        item.first_name,
                        item.last_name,
                        item.phone,
                        item.email,
                        item.zip,
                        item.city,
                        item.country,
                        item.address,
                        item.created_at,
                    ]
                )

        response = StreamingHttpResponse(iter_write(queryset), content_type="text/csv")
        response['Content-Disposition'] = f'attachment; filename="contacts.csv"'
        return response

    export_action.short_description = "Export contacts to CSV"


class UserDayStatAdmin(admin.ModelAdmin):
    list_display = (
        'account',
        'adaccount',
        'campaign',
        'user',
        'date',
        'cost',
        'spend',
        'payment',
        'funds',
        'visits',
        'clicks',
        'leads',
        'revenue',
        'profit',
    )
    list_filter = ('user',)
    search_fields = ('adaccount__name', 'campaign__name')
    raw_id_fields = ('account', 'adaccount', 'campaign', 'user')
    date_hierarchy = 'date'


class UserAccountDayStatAdmin(admin.ModelAdmin):
    list_display = (
        'account',
        'campaign',
        'user',
        'date',
        'cost',
        'spend',
        'payment',
        'funds',
        'visits',
        'clicks',
        'leads',
        'revenue',
        'profit',
    )
    list_filter = ('account__status', 'user')
    search_fields = ('campaign__name', 'campaign__symbol', 'account__id')
    raw_id_fields = ('account', 'campaign', 'user')
    date_hierarchy = 'date'


class UserAdAccountDayStatAdmin(admin.ModelAdmin):
    list_display = ('account', 'adaccount', 'user', 'date', 'spend', 'clicks')
    list_filter = ('account__status', 'user')
    raw_id_fields = ('account', 'adaccount', 'user')
    date_hierarchy = 'date'


class UserCampaignDayStatAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'user', 'date', 'visits', 'clicks', 'leads', 'revenue', 'cost', 'profit')
    search_fields = ('campaign__name',)
    list_filter = ('campaign__status', 'user')
    raw_id_fields = ('campaign', 'user')
    date_hierarchy = 'date'


class UserKPIAdmin(admin.ModelAdmin):
    list_display = ('metric', 'value', 'user', 'start_at', 'end_at')
    list_filter = ('metric', 'user')
    raw_id_fields = ('user',)


class CampaignTemplateAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'id',
        'user',
        'created_at',
    )
    list_filter = ('user',)
    raw_id_fields = ('user',)
    search_fields = ('name',)
    readonly_fields = ('created_at',)
    formfield_overrides = {JSONField: {'widget': JSONEditorWidget}}


class AdsCreateTaskAdmin(admin.ModelAdmin):
    list_display = ('account', 'adaccount', 'template', 'user', 'created_at', 'status', 'status_comment')
    raw_id_fields = ('account', 'adaccount', 'template')
    list_filter = ('user',)
    readonly_fields = ('created_at',)
    formfield_overrides = {JSONField: {'widget': JSONEditorWidget}}


class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('adaccount', 'display_string', 'card', 'time_created')


class CreditCardAdmin(admin.ModelAdmin):
    list_display = ('display_string', 'card_type', 'created_at', 'created_by', 'is_active', 'number')
    list_filter = ('card_type', 'created_by', 'is_active')
    search_fields = ('display_string', 'number', 'comment')
    list_editable = ('is_active',)
    date_hierarchy = 'created_at'


class AdAccountCreditCardAdmin(admin.ModelAdmin):
    list_display = (
        'account',
        'adaccount',
        'display_string',
        'credential_id',
        'spend',
        'fb_spends',
        'card',
        'created_at',
    )
    raw_id_fields = ('adaccount', 'card')
    date_hierarchy = 'created_at'
    search_fields = ('display_string',)

    def account(self, obj):
        return obj.adaccount.account.display_name

    account.short_description = 'Account'


class ProcessCSVTaskAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'file', 'created')
    list_filter = ('status',)


class AccountPaymentAdmin(admin.ModelAdmin):
    list_display = ('account', 'user', 'amount', 'amount_uah', 'date', 'created_at')
    list_filter = ('user',)
    date_hierarchy = 'date'


class FinAccountAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'description',
    )
    prepopulated_fields = {'slug': ('name',)}
    formfield_overrides = {JSONField: {'widget': JSONEditorWidget}}


admin.site.register(FinAccount, FinAccountAdmin)
admin.site.register(UserKPI, UserKPIAdmin)
admin.site.register(UserDayStat, UserDayStatAdmin)
admin.site.register(UserAccountDayStat, UserAccountDayStatAdmin)
admin.site.register(UserAdAccountDayStat, UserAdAccountDayStatAdmin)
admin.site.register(UserCampaignDayStat, UserCampaignDayStatAdmin)
admin.site.register(Card, CreditCardAdmin)
admin.site.register(AdAccountCreditCard, AdAccountCreditCardAdmin)

admin.site.register(Tag)
admin.site.register(Team)
admin.site.register(Country, CountryAdmin)
admin.site.register(PageCategory, PageCategoryAdmin)
admin.site.register(FieldsSetting, FieldsSettingAdmin)
admin.site.register(User, MyUserAdmin)
admin.site.register(Config, ConfigAdmin)
admin.site.register(NotificationSubscription)
admin.site.register(Action, ActionAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(FBPage, FBPageAdmin)
admin.site.register(Ad, AdAdmin)
admin.site.register(AdAccount, AdAccountAdmin)
admin.site.register(AdAccountTransaction, AdAccountTransactionAdmin)
admin.site.register(BusinessManager, BusinessManagerAdmin)
admin.site.register(BusinessManagerLog, BusinessManagerLogAdmin)
admin.site.register(BusinessShareUrl, BusinessShareUrlAdmin)
admin.site.register(AdAccountDayStat, AdAccountDayStatAdmin)
admin.site.register(Campaign, CampaignAdmin)
admin.site.register(Flow, FlowAdmin)
admin.site.register(Domain, DomainAdmin)
admin.site.register(ShortifyDomain, ShortifyDomainAdmin)
admin.site.register(FlowDayStat, FlowDayStatAdmin)
admin.site.register(CampaignDayStat, CampaignDayStatAdmin)
admin.site.register(AccountLog, AccountLogAdmin)
admin.site.register(CampaignLog, CampaignLogAdmin)
admin.site.register(AdAccountLog, AdAccountLogAdmin)
admin.site.register(UserRequest, UserRequestAdmin)
admin.site.register(UserRequestLog, UserRequestLogAdmin)
admin.site.register(AccountActivityLog, AccountActivityLogAdmin)

admin.site.register(ProcessCSVTask, ProcessCSVTaskAdmin)
admin.site.register(AccountPayment, AccountPaymentAdmin)
admin.site.register(Rule, RuleAdmin)
admin.site.register(Leadgen, LeadgenAdmin)
admin.site.register(PageLeadgen, PageLeadgenAdmin)
admin.site.register(LeadgenLead, LeadgenLeadAdmin)
admin.site.register(LinkGroup, LinkGroupAdmin)
admin.site.register(Link, LinkAdmin)
admin.site.register(LeadgenLeadConversion, LeadgenLeadConversionAdmin)
admin.site.register(CampaignTemplate, CampaignTemplateAdmin)
admin.site.register(AdsCreateTask, AdsCreateTaskAdmin)
admin.site.register(UploadedImage)
admin.site.register(UploadedVideo)

# Manychat + postbacks
admin.site.register(UserEmail, UserEmailAdmin)
admin.site.register(Contact, ContactAdmin)
