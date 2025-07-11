from typing import Any, Dict, Type

from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.fields import empty

from api.v1.serializers.accounts import AccountSimpleSerializer
from api.v1.serializers.adaccounts import AdAccountFinanceSerializer, AdAccountSimpleSerializer
from api.v1.serializers.users import AccountUserSerializer
from core.models.core import Account, AdAccount, BusinessManager, User, UserRequest


# TODO: Все это привести в нормальный вид
class UserMixin(serializers.BaseSerializer):
    def __init__(self, instance=None, data=empty, **kwargs):
        self.user = kwargs.pop('user', None)
        super(UserMixin, self).__init__(instance, data, **kwargs)


class MoneyRequestDataSerializer(UserMixin, serializers.Serializer):
    account = serializers.SerializerMethodField(allow_null=True, required=False)
    adaccount = serializers.SerializerMethodField(allow_null=True, required=False)
    business = serializers.SerializerMethodField(allow_null=True, required=False)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    actual_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    status_comment = serializers.CharField(max_length=512, allow_null=True, required=False)
    category = serializers.CharField()

    def get_account(self, obj):
        # TODO: cache
        if 'account_id' in obj:
            try:
                account = Account.objects.get(id=obj.pop('account_id'))
                return AccountSimpleSerializer(account).data
            except Account.DoesNotExist:
                raise ValidationError('Account not found')
        return None

    def get_adaccount(self, obj):
        # TODO: cache
        if 'adaccount_id' in obj:
            try:
                adaccount = AdAccount.objects.get(id=obj.pop('adaccount_id'))
                if self.user.role in [User.ADMIN, User.FINANCIER]:
                    return AdAccountFinanceSerializer(adaccount).data
                return AdAccountSimpleSerializer(adaccount).data
            except AdAccount.DoesNotExist:
                pass
        return None

    def get_business(self, obj):
        # TODO: cache
        if 'business_id' in obj:
            try:
                business = BusinessManager.objects.get(id=obj.pop('business_id'))
                return {'id': business.id, 'business_id': business.business_id, 'name': business.name}
            except BusinessManager.DoesNotExist:
                pass
        return None


class AccountRequestDataSerializer(UserMixin, serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=20)
    category = serializers.CharField(default='account')
    actual_quantity = serializers.IntegerField(min_value=1, max_value=20, required=False)
    status_comment = serializers.CharField(max_length=512, allow_null=True, required=False)


class FixRequestDataSerializer(UserMixin, serializers.Serializer):
    account = serializers.SerializerMethodField(allow_null=True, required=False)
    adaccount = serializers.SerializerMethodField(allow_null=True, required=False)
    business = serializers.SerializerMethodField(allow_null=True, required=False)
    status_comment = serializers.CharField(max_length=512, allow_null=True, required=False)
    category = serializers.CharField(default='finances')

    def get_account(self, obj):
        if 'account_id' in obj:
            try:
                account = Account.objects.get(id=obj.pop('account_id'))
                return AccountSimpleSerializer(account).data
            except Account.DoesNotExist:
                raise ValidationError('Account not found')
        return None

    def get_adaccount(self, obj):
        # TODO: cache
        if 'adaccount_id' in obj:
            try:
                adaccount = AdAccount.objects.get(id=obj.pop('adaccount_id'))
                if self.user.role in [User.ADMIN, User.FINANCIER]:
                    return AdAccountFinanceSerializer(adaccount).data
                return AdAccountSimpleSerializer(adaccount).data
            except AdAccount.DoesNotExist:
                pass
        return None

    def get_business(self, obj):
        # TODO: cache
        if 'business_id' in obj:
            try:
                business = BusinessManager.objects.get(id=obj.pop('business_id'))
                return {'id': business.id, 'business_id': business.business_id, 'name': business.name}
            except BusinessManager.DoesNotExist:
                pass
        return None


class SetupRequestDataSerializer(UserMixin, serializers.Serializer):
    account = serializers.SerializerMethodField(allow_null=True, required=False)
    adaccount = serializers.SerializerMethodField(allow_null=True, required=False)
    business = serializers.SerializerMethodField(allow_null=True, required=False)
    status_comment = serializers.CharField(max_length=512, allow_null=True, required=False)

    def get_account(self, obj):
        # TODO: cache
        if 'account_id' in obj:
            try:
                account = Account.objects.get(id=obj.pop('account_id'))
                return AccountSimpleSerializer(account).data
            except Account.DoesNotExist:
                raise ValidationError('Account not found')
        return None

    def get_adaccount(self, obj):
        # TODO: cache
        if 'adaccount_id' in obj:
            try:
                adaccount = AdAccount.objects.get(id=obj.pop('adaccount_id'))
                if self.user.role in [User.ADMIN, User.FINANCIER]:
                    return AdAccountFinanceSerializer(adaccount).data
                return AdAccountSimpleSerializer(adaccount).data
            except AdAccount.DoesNotExist:
                pass
        return None

    def get_business(self, obj):
        # TODO: cache
        if 'business_id' in obj:
            try:
                business = BusinessManager.objects.get(id=obj.pop('business_id'))
                return {'id': business.id, 'business_id': business.business_id, 'name': business.name}
            except BusinessManager.DoesNotExist:
                pass
        return None


class BaseUserRequestListSerializer(UserMixin, serializers.ModelSerializer):
    request_data = serializers.SerializerMethodField()
    processed_by = AccountUserSerializer(read_only=True)

    def get_data_serializer_class(self, request_type: str) -> Type[serializers.Serializer]:
        if request_type == 'money':
            return MoneyRequestDataSerializer
        elif request_type == 'fix':
            return FixRequestDataSerializer
        elif request_type == 'accounts':
            return AccountRequestDataSerializer
        elif request_type == 'setup':
            return SetupRequestDataSerializer
        raise ValidationError('Wrong request type')

    def get_request_data(self, obj) -> Dict[str, Any]:
        return self.get_data_serializer_class(obj.request_type)(obj.request_data, user=self.user).data

    class Meta:
        model = UserRequest
        exclude = ('updated_at',)


class UserRequestListAdminSerializer(BaseUserRequestListSerializer):
    user = AccountUserSerializer(read_only=True)


class UserRequestListMediabuyerSerializer(BaseUserRequestListSerializer):
    pass


class UserRequestListFarmerSerializer(BaseUserRequestListSerializer):
    pass


class UserRequestListTeamleadSerializer(BaseUserRequestListSerializer):
    user = AccountUserSerializer(read_only=True)


class UserRequestListManagerSerializer(UserRequestListMediabuyerSerializer):
    user = AccountUserSerializer(read_only=True)


class UserRequestListSetuperSerializer(BaseUserRequestListSerializer):
    user = AccountUserSerializer(read_only=True)


# Serializers for validation different type of requests
class MoneyRequestCreateDataSerializer(UserMixin, serializers.Serializer):
    MONEYREQUEST_CATEGORY_CHOICES = (('general', _('General')), ('topup', _('Account Topup')))

    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    account_id = serializers.IntegerField(allow_null=True, required=False)
    adaccount_id = serializers.IntegerField(allow_null=True, required=False)
    business_id = serializers.IntegerField(allow_null=True, required=False)

    category = serializers.ChoiceField(choices=MONEYREQUEST_CATEGORY_CHOICES)

    def validate(self, attrs):
        validated = super(MoneyRequestCreateDataSerializer, self).validate(attrs)
        # if not any(x in validated for x in ['account_id', 'adaccount_id', 'business_id']):
        #     raise ValidationError('Set account_id or adaccount_id or business_id')

        if 'account_id' in validated:
            try:
                account = Account.objects.get(id=validated['account_id'])
            except Account.DoesNotExist:
                raise ValidationError('Bad Request')

            # if not account.fb_access_token:
            #     raise ValidationError('Set fb access token to the account!')

            if self.user.role not in [User.ADMIN, User.FINANCIER, User.MANAGER] and account.manager != self.user:
                raise PermissionDenied('You should be manager of the account')

            return validated

        elif 'adaccount_id' in validated:
            try:
                adaccount = AdAccount.objects.get(id=validated['adaccount_id'])
                # if not adaccount.account.fb_access_token:
                #     raise ValidationError('Set fb access token to the account!')
                validated['business_id'] = adaccount.business_id
                validated['account_id'] = adaccount.account_id
            except AdAccount.DoesNotExist:
                raise ValidationError('Bad adaccount')

        elif 'business_id' in validated:
            try:
                business = BusinessManager.objects.get(id=validated['business_id'])
                # if not business.account.fb_access_token:
                #     raise ValidationError('Set fb access token to the account!')
                validated['account_id'] = business.account_id
            except AdAccount.DoesNotExist:
                raise ValidationError('Bad adaccount')

        return validated


class FixRequestCreateDataSerializer(UserMixin, serializers.Serializer):
    FIXREQUEST_CATEGORY_CHOICES = (('finances', _('Finances')), ('docs', _('Docs')))

    account_id = serializers.IntegerField(allow_null=True, required=False)
    adaccount_id = serializers.IntegerField(allow_null=True, required=False)
    business_id = serializers.IntegerField(allow_null=True, required=False)
    category = serializers.ChoiceField(choices=FIXREQUEST_CATEGORY_CHOICES)

    # TODO: validate manager
    def validate(self, attrs):
        validated = super(FixRequestCreateDataSerializer, self).validate(attrs)
        if not any(x in validated for x in ['account_id', 'adaccount_id', 'business_id']):
            raise ValidationError('Set account_id or adaccount_id or business_id')

        # if 'account_id' in validated:
        #     account = Account.objects.get(id=validated['account_id'])
        # if not account.fb_access_token:
        #     raise ValidationError('Set fb access token to the account!')

        if 'adaccount_id' in validated:
            try:
                adaccount = AdAccount.objects.get(id=validated['adaccount_id'])
                # if not adaccount.account.fb_access_token:
                #     raise ValidationError('Set fb access token to the account!')
                validated['business_id'] = adaccount.business_id
                validated['account_id'] = adaccount.account_id
            except AdAccount.DoesNotExist:
                raise ValidationError('Bad adaccount')

        elif 'business_id' in validated:
            try:
                business = BusinessManager.objects.get(id=validated['business_id'])
                # if not business.account.fb_access_token:
                #     raise ValidationError('Set fb access token to the account!')

                validated['account_id'] = business.account_id
            except AdAccount.DoesNotExist:
                raise ValidationError('Bad adaccount')

        return validated


class AccountRequestCreateDataSerializer(UserMixin, serializers.Serializer):
    ACCOUNTREQUEST_CATEGORY_CHOICES = (
        ('account', _('Account')),
        ('bm', _('Business Manager')),
    )
    quantity = serializers.IntegerField(min_value=1, max_value=20)
    category = serializers.ChoiceField(choices=ACCOUNTREQUEST_CATEGORY_CHOICES)


class SetupRequestCreateDataSerializer(UserMixin, serializers.Serializer):
    account_id = serializers.IntegerField(allow_null=True, required=False)
    adaccount_id = serializers.IntegerField(allow_null=True, required=False)
    business_id = serializers.IntegerField(allow_null=True, required=False)

    # TODO: validate manager
    def validate(self, attrs):
        validated = super(SetupRequestCreateDataSerializer, self).validate(attrs)
        if not any(x in validated for x in ['account_id', 'adaccount_id', 'business_id']):
            raise ValidationError('Set account_id or adaccount_id or business_id')

        if 'account_id' in validated:
            account = Account.objects.get(id=validated['account_id'])
            if not account.fb_access_token:
                raise ValidationError('Set fb access token to the account!')

        elif 'adaccount_id' in validated:
            try:
                adaccount = AdAccount.objects.get(id=validated['adaccount_id'])
                if not adaccount.account.fb_access_token:
                    raise ValidationError('Set fb access token to the account!')
                validated['business_id'] = adaccount.business_id
                validated['account_id'] = adaccount.account_id
            except AdAccount.DoesNotExist:
                raise ValidationError('Bad adaccount')

        elif 'business_id' in validated:
            try:
                business = BusinessManager.objects.get(id=validated['business_id'])
                if not business.account.fb_access_token:
                    raise ValidationError('Set fb access token to the account!')
                validated['account_id'] = business.account_id
            except AdAccount.DoesNotExist:
                raise ValidationError('Bad adaccount')

        return validated


class UserRequestCreateSerializer(UserMixin, serializers.ModelSerializer):
    def get_data_serializer_class(self, request_type: str) -> Type[serializers.Serializer]:
        if request_type == 'money':
            return MoneyRequestCreateDataSerializer
        elif request_type == 'fix':
            return FixRequestCreateDataSerializer
        elif request_type == 'accounts':
            return AccountRequestCreateDataSerializer
        elif request_type == 'setup':
            return SetupRequestCreateDataSerializer
        else:
            raise ValidationError('Wrong request type')

    def validate(self, attrs):
        validated_data = super(UserRequestCreateSerializer, self).validate(attrs)
        # Validate data для разных типов реквестов
        if self.user.role == User.SETUPER and validated_data['request_type'] == 'setup':
            raise ValidationError('Wrong request_type for this user')

        serializer = self.get_data_serializer_class(validated_data['request_type'])(
            user=self.context['request'].user, data=validated_data['request_data']
        )
        serializer.is_valid(raise_exception=True)
        validated_data['request_data'] = serializer.validated_data
        return validated_data

    class Meta:
        model = UserRequest
        fields = ('request_type', 'request_data', 'comment')


# TODO: Validate diff types
class UserRequestUpdateSerializer(UserMixin, serializers.ModelSerializer):
    processed_by = AccountUserSerializer(read_only=True)

    def validate(self, attrs):
        validated = super(UserRequestUpdateSerializer, self).validate(attrs)
        if (
            self.instance.request_type == 'setup'  # type: ignore
            and self.instance.user != self.user  # type: ignore
            and self.user.role not in [User.ADMIN, User.SETUPER]
        ):
            raise ValidationError('Wrong action for this user')
        return validated

    class Meta:
        model = UserRequest
        fields = ('status', 'request_data', 'processed_by')
