from decimal import Decimal
from typing import Any

from django.utils.duration import duration_string

from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers

from api.v1.serializers.campaigns import CampaignListSerializer
from api.v1.serializers.users import AccountUserSerializer
from api.v1.utils import ACCOUNT_FIELDS_BY_ROLE
from core.models import User
from core.models.core import Account, AccountLog, AccountPayment, Campaign, ProcessCSVTask, Tag, UploadedImage


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('name',)


class AccountCreateSerializer(serializers.ModelSerializer):
    supplier = serializers.PrimaryKeyRelatedField(
        required=False, queryset=User.objects.filter(role=User.SUPPLIER, is_active=True)
    )

    class Meta:
        model = Account
        fields = (
            'login',
            'password',
            'price',
            'tags',
            'country_code',
            'mla_profile_id',
            'comment',
            'supplier',
            'fb_access_token',
        )


class SimpleStatusSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='get_status_display', read_only=True)
    status_duration = serializers.DurationField(read_only=True)

    class Meta:
        model = Account
        fields = ('title', 'status_duration', 'status')


class AccountSimpleSerializer(serializers.ModelSerializer):
    is_banned = serializers.SerializerMethodField(read_only=True)
    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        return SimpleStatusSerializer(obj).data

    def get_is_banned(self, obj):
        return True if obj.status == Account.BANNED else False

    class Meta:
        model = Account
        fields = ('id', 'country_code', 'tags', 'is_banned', 'status')


class AccountStatusSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='get_status_display', read_only=True)
    status_duration = serializers.DurationField(read_only=True)
    last_status = serializers.IntegerField(read_only=True)
    available_statuses = serializers.SerializerMethodField(read_only=True)

    def get_available_statuses(self, obj):
        return obj.get_available_statuses(user=self.context['request'].user)

    # def validate(self, attrs):
    #     validated = super(AccountStatusSerializer, self).validate(attrs)
    #
    #     if 'status' in validated:
    #         if self.instance.status == validated['status']:
    #             raise ValidationError('Can not change to the same status! Reload the page to see actual data.')
    #
    #     return validated

    class Meta:
        model = Account
        fields = ('id', 'status', 'title', 'status_comment', 'status_duration', 'available_statuses', 'last_status')


# List Account Serializers
class BaseAccountListSerializer(FlexFieldsModelSerializer):
    status = serializers.SerializerMethodField()
    auth = serializers.SerializerMethodField()
    account = serializers.SerializerMethodField()

    def get_account(self, obj):
        return {
            'id': obj.id,
            'country_code': obj.country_code,
            'tags': obj.tags,
            'has_token': True if obj.fb_access_token else False,
            'has_campaign': obj.has_campaign,
        }

    def get_status(self, obj):
        return {
            'status': obj.status,
            'title': obj.get_status_display(),
            'status_comment': obj.status_comment,
            'status_duration': duration_string(obj.status_duration),
            'available_statuses': obj.get_available_statuses(user=self.context['request'].user),
            'last_status': obj.last_status,
        }

    def get_auth(self, obj):
        return {'login': obj.login, 'password': obj.password}

    #
    # def get_financial(self, obj):
    #     return {'card_number': obj.card_number, 'financial_comment': obj.financial_comment}

    def get_created(self, obj):
        return {
            'created_by': {
                'id': obj.created_by_id,
                'display_name': obj.created_by.display_name,
                'photo_url': obj.created_by.photo_url,
            },
            'created_at': obj.created_at,
        }

    def get_payments(self, obj):
        return {'price': obj.price, 'total_paid': obj.total_paid, 'paid_till': obj.paid_till}

    def get_spends(self, obj):
        return {
            'fb_spends': obj.fb_spends,
            'fb_spends_today': obj.fb_spends_today,
            'fb_spends_yesterday': obj.fb_spends_yesterday,
        }

    def get_funds(self, obj):
        return {'total_funds': obj.total_funds, 'funds_wait': obj.funds_wait, 'last_funded': obj.last_funded}

    class Meta:
        model = Account


class AccountListAdminSerializer(BaseAccountListSerializer):
    manager = AccountUserSerializer(read_only=True)
    supplier = AccountUserSerializer(read_only=True)
    created = serializers.SerializerMethodField()
    # financial = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()
    spends = serializers.SerializerMethodField()
    funds = serializers.SerializerMethodField()

    class Meta(BaseAccountListSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.ADMIN]['list']


class AccountListMediabuyerSerializer(BaseAccountListSerializer):
    spends = serializers.SerializerMethodField()
    funds = serializers.SerializerMethodField()

    class Meta(BaseAccountListSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.MEDIABUYER]['list']


class AccountListTeamleadSerializer(AccountListMediabuyerSerializer):
    manager = AccountUserSerializer(read_only=True)

    class Meta(AccountListMediabuyerSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.TEAMLEAD]['list']


class AccountListFinancierSerializer(BaseAccountListSerializer):
    manager = AccountUserSerializer(read_only=True)
    supplier = AccountUserSerializer(read_only=True)
    payments = serializers.SerializerMethodField()
    spends = serializers.SerializerMethodField()
    funds = serializers.SerializerMethodField()

    class Meta(BaseAccountListSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.FINANCIER]['list']


class AccountListFarmerSerializer(BaseAccountListSerializer):
    spends = serializers.SerializerMethodField()
    funds = serializers.SerializerMethodField()

    class Meta(BaseAccountListSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.FARMER]['list']


class AccountListSupplierSerializer(BaseAccountListSerializer):
    payments = serializers.SerializerMethodField()

    class Meta(BaseAccountListSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SUPPLIER]['list']


class AccountListSupplierTeamleadSerializer(BaseAccountListSerializer):
    payments = serializers.SerializerMethodField()
    supplier = AccountUserSerializer(read_only=True)

    class Meta(BaseAccountListSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SUPPLIER_TEAMLEAD]['list']


class AccountListSetuperSerializer(BaseAccountListSerializer):
    manager = AccountUserSerializer(read_only=True)

    class Meta(BaseAccountListSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SETUPER]['list']


class AccountListManagerSerializer(BaseAccountListSerializer):
    spends = serializers.SerializerMethodField()
    funds = serializers.SerializerMethodField()
    manager = AccountUserSerializer(read_only=True)
    supplier = AccountUserSerializer(read_only=True)
    created = serializers.SerializerMethodField()

    class Meta(BaseAccountListSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.MANAGER]['list']


# Edit Account Serializers
# TODO: Универсальный класс для всех одинаковых сериализаторов
# TODO: Валидация владельца кампании
class AccountEditAdminSerializer(serializers.ModelSerializer):
    manager = serializers.PrimaryKeyRelatedField(
        write_only=True,
        queryset=User.objects.filter(
            role__in=[
                User.ADMIN,
                User.MEDIABUYER,
                User.FARMER,
                User.SETUPER,
                User.MANAGER,
                User.TEAMLEAD,
                User.JUNIOR,
            ],
            is_active=True,
        ),
        allow_null=True,
        allow_empty=True,
    )

    campaign = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Campaign.objects.all(), allow_null=True, allow_empty=True
    )

    supplier = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=User.objects.filter(role=User.SUPPLIER, is_active=True)
    )
    card_balance = serializers.DecimalField(allow_null=True, max_digits=10, decimal_places=2)

    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS_BY_ROLE[User.ADMIN]['edit']


class AccountEditSupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SUPPLIER]['edit']


class AccountEditSupplierTeamleadSerializer(serializers.ModelSerializer):
    supplier = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=User.objects.filter(role__in=[User.SUPPLIER, User.SUPPLIER_TEAMLEAD], is_active=True)
    )

    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SUPPLIER_TEAMLEAD]['edit']


class AccountEditSetuperSerializer(serializers.ModelSerializer):
    campaign = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Campaign.objects.all(), allow_null=True, allow_empty=True
    )

    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SETUPER]['edit']


class AccountEditMediabuyerSerializer(serializers.ModelSerializer):
    campaign = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Campaign.objects.all(), allow_null=True, allow_empty=True
    )

    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS_BY_ROLE[User.MEDIABUYER]['edit']


class AccountEditTeamleadSerializer(AccountEditMediabuyerSerializer):
    class Meta(AccountEditMediabuyerSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.TEAMLEAD]['edit']


class AccountEditFarmerSerializer(serializers.ModelSerializer):
    campaign = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Campaign.objects.all(), allow_null=True, allow_empty=True
    )

    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS_BY_ROLE[User.FARMER]['edit']


class AccountEditFinancierSerializer(serializers.ModelSerializer):
    campaign = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Campaign.objects.all(), allow_null=True, allow_empty=True
    )
    card_balance = serializers.DecimalField(allow_null=True, max_digits=10, decimal_places=2)

    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS_BY_ROLE[User.FINANCIER]['edit']


class AccountEditManagerSerializer(serializers.ModelSerializer):
    manager = serializers.PrimaryKeyRelatedField(
        write_only=True,
        queryset=User.objects.filter(
            role__in=[
                User.ADMIN,
                User.MEDIABUYER,
                User.FARMER,
                User.SETUPER,
                User.MANAGER,
                User.TEAMLEAD,
                User.JUNIOR,
            ],
            is_active=True,
        ),
        allow_null=True,
        allow_empty=True,
    )

    supplier = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=User.objects.filter(role=User.SUPPLIER, is_active=True)
    )

    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS_BY_ROLE[User.MANAGER]['edit']


# Retrieve Account Serializers
# TODO: Универсальный класс для всех одинаковых сериализаторов
class BaseAccountRetrieveSerializer(FlexFieldsModelSerializer):
    status_duration = serializers.DurationField(read_only=True)
    last_status = serializers.IntegerField(read_only=True)
    campaign = CampaignListSerializer(read_only=True)
    age = serializers.DurationField(read_only=True)
    has_campaign = serializers.BooleanField(read_only=True)
    available_statuses = serializers.SerializerMethodField(read_only=True)

    def get_available_statuses(self, obj):
        return obj.get_available_statuses(user=self.context['request'].user)

    class Meta:
        model = Account


class AccountRetrieveAdminSerializer(BaseAccountRetrieveSerializer):
    manager = AccountUserSerializer(read_only=True)
    supplier = AccountUserSerializer(read_only=True)
    created_by = AccountUserSerializer(read_only=True)

    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.ADMIN]['retrieve']


class AccountRetrieveSupplierSerializer(BaseAccountRetrieveSerializer):
    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SUPPLIER]['retrieve']


class AccountRetrieveSupplierTeamleadSerializer(BaseAccountRetrieveSerializer):
    supplier = AccountUserSerializer(read_only=True)

    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SUPPLIER_TEAMLEAD]['retrieve']


class AccountRetrieveSetuperSerializer(BaseAccountRetrieveSerializer):
    manager = AccountUserSerializer(read_only=True)

    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.SETUPER]['retrieve']


class AccountRetrieveFarmerSerializer(BaseAccountRetrieveSerializer):
    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.FARMER]['retrieve']


class AccountRetrieveMediabuyerSerializer(BaseAccountRetrieveSerializer):
    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.MEDIABUYER]['retrieve']


class AccountRetrieveTeamleadSerializer(BaseAccountRetrieveSerializer):
    manager = AccountUserSerializer(read_only=True)

    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.TEAMLEAD]['retrieve']


class AccountRetrieveFinancierSerializer(BaseAccountRetrieveSerializer):
    manager = AccountUserSerializer(read_only=True)
    created_by = AccountUserSerializer(read_only=True)

    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.FINANCIER]['retrieve']


class AccountRetrieveManagerSerializer(BaseAccountRetrieveSerializer):
    manager = AccountUserSerializer(read_only=True)
    created_by = AccountUserSerializer(read_only=True)
    supplier = AccountUserSerializer(read_only=True)

    class Meta(BaseAccountRetrieveSerializer.Meta):
        fields = ACCOUNT_FIELDS_BY_ROLE[User.MANAGER]['retrieve']


class AccountLogSerializer(serializers.ModelSerializer):
    manager = AccountUserSerializer(read_only=True)
    changed_by = AccountUserSerializer(read_only=True)

    class Meta:
        model = AccountLog
        fields = ('start_at', 'end_at', 'status', 'manager', 'changed_by')


class AccountStatusDurationStatsSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    duration = serializers.DurationField()


class FanPageCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=64)
    image = serializers.PrimaryKeyRelatedField(write_only=True, queryset=UploadedImage.objects.all(), many=True)
    category = serializers.IntegerField()


class BusinessCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=64)


class ImportCSVTaskSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)

    class Meta:
        model = ProcessCSVTask
        fields = ('file', 'type')


class AccountPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountPayment
        fields = ('date', 'amount', 'amount_uah')


class AccountPaymentHistoryTotalSerializer(serializers.Serializer):
    total_amount_usd = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount_uah = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)


class AccountPaymentHistorySerializer(serializers.Serializer):
    date = serializers.DateField()
    amount_usd = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_uah = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    accounts = serializers.IntegerField()


class AccountPaymentTotalSerializer(serializers.Serializer):
    total_payments = serializers.DecimalField(allow_null=True, max_digits=10, decimal_places=2)
    total_accounts = serializers.IntegerField(default=0)


class AccountPaymentDataSerializer(serializers.Serializer):
    duration = serializers.DurationField()
    day_duration = serializers.IntegerField()
    account = AccountSimpleSerializer()
    payment = serializers.DecimalField(allow_null=True, max_digits=10, decimal_places=2)
    day_price = serializers.DecimalField(allow_null=True, max_digits=10, decimal_places=2)
    week_price = serializers.DecimalField(allow_null=True, max_digits=10, decimal_places=2)
    supplier = AccountUserSerializer(allow_null=True, required=False)
    paid_till = serializers.DateTimeField()

    def to_representation(self, instance: Any) -> Any:
        data = super(AccountPaymentDataSerializer, self).to_representation(instance)
        if instance['account'].status == Account.ON_VERIFY:
            data['payment'] = Decimal('0.00')
        return data


class AccountPaymentDoneAccountSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    amount = serializers.DecimalField(allow_null=True, max_digits=10, decimal_places=2)


class AccountPaymentDoneSerializer(serializers.Serializer):
    currency_rate = serializers.DecimalField(max_digits=10, decimal_places=2)
    pay_till = serializers.DateField()
    accounts = AccountPaymentDoneAccountSerializer(many=True)
