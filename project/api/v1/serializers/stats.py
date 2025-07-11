from rest_framework import serializers

from api.v1.serializers.accounts import AccountSimpleSerializer
from api.v1.serializers.adaccounts import AdAccountSimpleSerializer
from api.v1.serializers.core import FlowSerializer
from api.v1.serializers.users import AccountUserSerializer
from core.models.core import Account, AdAccount, Campaign, Flow, User


class StatsCalcsMetricsMixin(serializers.Serializer):
    epc = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    roi = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    cv = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    cr = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    ctr = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)


class BaseStatsSerializerMixin(serializers.Serializer):
    visits = serializers.IntegerField()
    clicks = serializers.IntegerField()
    leads = serializers.IntegerField()

    revenue = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    spend = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    profit = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)

    def get_campaign(self, obj):
        campaign_id = obj.pop('campaign_id')
        campaign = Campaign.objects.filter(id=campaign_id).first()
        if campaign:
            return {'id': campaign.id, 'name': campaign.name, 'country_code': campaign.country_code}
        return None

    def get_account(self, obj):
        account_id = obj.pop('account_id')
        account = Account.objects.filter(id=account_id).first()
        if account:
            return AccountSimpleSerializer(account).data
        return None

    def get_adaccount(self, obj):
        adaccount_id = obj.pop('adaccount_id')
        adaccount = AdAccount.objects.filter(id=adaccount_id).first()
        if adaccount:
            return AdAccountSimpleSerializer(adaccount).data
        return None

    def get_user(self, obj):
        user_id = obj.pop('user_id')
        user = User.objects.filter(id=user_id).first()
        if user:
            return AccountUserSerializer(user).data
        return None

    def get_flow(self, obj):
        flow_id = obj.pop('flow_id')
        flow = Flow.objects.filter(id=flow_id).first()
        if flow:
            return FlowSerializer(flow).data
        return None


class TotalStatsSerializerMixin(StatsCalcsMetricsMixin):
    total_visits = serializers.IntegerField()
    total_clicks = serializers.IntegerField()
    total_leads = serializers.IntegerField()

    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_spend = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_profit = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_payment = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)


class DateStatSerializer(BaseStatsSerializerMixin, StatsCalcsMetricsMixin):
    date = serializers.DateField()


class CampaignStatSerializer(BaseStatsSerializerMixin, StatsCalcsMetricsMixin):
    campaign_id = serializers.IntegerField()
    campaign = serializers.SerializerMethodField()


class AccountStatSerializer(BaseStatsSerializerMixin, StatsCalcsMetricsMixin):
    account_id = serializers.IntegerField()
    account = serializers.SerializerMethodField()


class AdAccountStatSerializer(BaseStatsSerializerMixin, StatsCalcsMetricsMixin):
    adaccount_id = serializers.IntegerField()
    adaccount = serializers.SerializerMethodField()


class FlowStatSerializer(BaseStatsSerializerMixin, StatsCalcsMetricsMixin):
    flow_id = serializers.IntegerField()
    flow = serializers.SerializerMethodField()


# TODO: FIXME
class UsersStatSerializer(BaseStatsSerializerMixin, StatsCalcsMetricsMixin):
    user_id = serializers.IntegerField()
    user = serializers.SerializerMethodField()


class LeadgenLeadStatsSerializer(serializers.Serializer):
    date = serializers.DateField()
    leads = serializers.IntegerField()
