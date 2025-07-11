import datetime
import hashlib
import hmac
import time

from django.conf import settings
from django.contrib.auth import authenticate

from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.models import User
from core.models.core import NotificationSubscription, Team


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        user = authenticate(**data)
        if user and user.is_active:
            return user
        raise serializers.ValidationError("Incorrect Credentials")


class TelegramInputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    username = serializers.CharField(required=False)
    photo_url = serializers.CharField(required=False)
    auth_date = serializers.CharField()
    hash = serializers.CharField()

    def validate(self, attrs):
        validated = super(TelegramInputSerializer, self).validate(attrs)

        bot_token = settings.TELEGRAM_BOT_TOKEN

        received_hash_string = validated.get('hash')
        auth_date = validated.get('auth_date')

        check_string_list = ['{}={}'.format(k, v) for k, v in validated.items() if k != 'hash']
        check_string = '\n'.join(sorted(check_string_list))
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        built_hash = hmac.new(secret_key, msg=check_string.encode(), digestmod=hashlib.sha256).hexdigest()
        current_timestamp = int(time.time())
        auth_timestamp = int(auth_date)
        if current_timestamp - auth_timestamp > 86400:
            raise ValidationError('telegram', 'Auth date is outdated')
        if built_hash != received_hash_string:
            raise ValidationError('telegram', 'Invalid hash supplied')
        return validated


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ('id', 'name')


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    password1 = serializers.CharField(write_only=True)
    team = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Team.objects.all(), allow_null=True, allow_empty=True
    )

    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'role',
            'team',
            'password',
            'password1',
            'tracker_login',
            'tracker_password',
            'proxy_host',
            'proxy_port',
            'proxy_login',
            'proxy_password',
            'mla_group_id',
        )

    def validate(self, attrs):
        validated = super(UserCreateSerializer, self).validate(attrs)
        if validated['password'] != validated.pop('password1'):
            raise serializers.ValidationError('Passwords do not match!')
        return validated

    def create(self, validated_data):
        user = super(UserCreateSerializer, self).create(validated_data)
        user.set_password(validated_data['password'])
        user.save()
        return user


class UserSimpleSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'display_name')


class UserListSerializer(FlexFieldsModelSerializer):
    team = TeamSerializer()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'role',
            'team',
            'photo_url',
            'display_name',
            'is_active',
            'active_accounts',
            'banned_accounts',
            'onverify_accounts',
        )


class UserRetrieveSerializer(FlexFieldsModelSerializer):
    team = TeamSerializer()

    # TODO: Fix for admin only fields
    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'date_joined',
            'email',
            'role',
            'team',
            'photo_url',
            'display_name',
            'is_active',
            'active_accounts',
            'banned_accounts',
            'onverify_accounts',
            'proxy_host',
            'proxy_port',
            'proxy_login',
            'proxy_password',
            'tracker_login',
            'tracker_password',
            'mla_group_id',
        )


class UserChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password1 = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate(self, attrs):
        validated = super(UserChangePasswordSerializer, self).validate(attrs)
        if not self.instance or not self.instance.check_password(validated.get('old_password')):
            raise serializers.ValidationError('Wrong old password')

        if validated.get('password') != validated.get('password1'):
            raise serializers.ValidationError('Passwords does not match!')
        return validated


class UserEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'is_active',
            'email',
            'tracker_login',
            'tracker_password',
            'proxy_host',
            'proxy_port',
            'proxy_login',
            'proxy_password',
        ]


class UserEditAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'is_active',
            'email',
            'tracker_login',
            'tracker_password',
            'proxy_host',
            'proxy_port',
            'proxy_login',
            'proxy_password',
            'role',
            'is_active',
            'team',
            'mla_group_id',
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    display_role = serializers.CharField(source='get_role_display')
    team = TeamSerializer()

    class Meta:
        model = User
        fields = (
            'id',
            'role',
            'display_role',
            'display_name',
            'photo_url',
            'team',
            'email',
            'first_name',
            'last_name',
        )


class AccountUserSerializer(serializers.ModelSerializer):
    team = TeamSerializer()

    class Meta:
        model = User
        fields = ('id', 'display_name', 'role', 'photo_url', 'team')


#
# class AccountCreatedBySerializer(serializers.ModelSerializer):
#     class Meta:
#         model = User
#         fields = ('id', 'display_name', 'photo_url')


class UserStatSerializer(serializers.ModelSerializer):
    month_profit = serializers.DecimalField(max_digits=10, decimal_places=2)
    day_profit = serializers.DecimalField(max_digits=10, decimal_places=2)
    day_leads = serializers.IntegerField()
    month_leads = serializers.IntegerField()

    class Meta:
        model = User
        fields = ('id', 'role', 'display_name', 'photo_url', 'day_profit', 'month_profit', 'day_leads', 'month_leads')


class TeamStatSerializer(serializers.ModelSerializer):
    month_profit = serializers.DecimalField(max_digits=10, decimal_places=2)
    day_profit = serializers.DecimalField(max_digits=10, decimal_places=2)
    day_leads = serializers.IntegerField()
    month_leads = serializers.IntegerField()

    class Meta:
        model = Team
        fields = ('id', 'name', 'day_profit', 'month_profit', 'day_leads', 'month_leads')


class UserCorrectionSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    field = serializers.CharField()
    value = serializers.DecimalField(max_digits=10, decimal_places=2)


class NotificationSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSubscription
        fields = ('level', 'channel')


class RoleSerializer(serializers.Serializer):
    """
    Fake serializer for swagger fake view
    """

    pass


# Придумать получше
class MediabuyerTotalStatsSerializer(serializers.Serializer):
    profit = serializers.DecimalField(max_digits=10, decimal_places=2)
    spend = serializers.DecimalField(max_digits=10, decimal_places=2)
    banned_accs = serializers.IntegerField(default=0)
    leads = serializers.IntegerField(default=0)
    bms = serializers.IntegerField(default=0)
    adaccounts = serializers.IntegerField(default=0)
    roi = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    avg_accs_lifetime = serializers.FloatField(default=0.0)
    statuses = serializers.ListField(default=[])


# Придумать получше
class FarmerTotalStatsSerializer(serializers.Serializer):
    on_farm = serializers.IntegerField(default=0)
    farmed = serializers.IntegerField(default=0)
    banned = serializers.IntegerField(default=0)
    avg_sessions = serializers.IntegerField(default=0)
    total_sessions = serializers.IntegerField(default=0)
    avg_profit = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    avg_spend = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    avg_age = serializers.DurationField(default=datetime.timedelta(0))
    avg_surfing = serializers.DurationField(default=datetime.timedelta(0))
    avg_session_duration = serializers.DurationField(default=datetime.timedelta(0))


class UserDayStatsSerializer(serializers.Serializer):
    profit = serializers.DecimalField(max_digits=10, decimal_places=2)
    spend = serializers.DecimalField(max_digits=10, decimal_places=2)
    revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    date = serializers.DateField()
