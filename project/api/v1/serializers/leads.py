from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers

from api.v1.serializers.accounts import AccountSimpleSerializer
from api.v1.serializers.core import CountrySerializer
from api.v1.serializers.users import AccountUserSerializer
from core.models.core import LeadgenLead, LinkGroup


class LinkGroupListSerializer(FlexFieldsModelSerializer):
    user = AccountUserSerializer(read_only=True)
    status = serializers.SerializerMethodField()
    click_rate = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    unique_clicks = serializers.IntegerField(source='clicked_links', read_only=True)

    def get_status(self, obj):
        return {
            'status': obj.status,
            'title': obj.get_status_display(),
            'status_comment': obj.status_comment,
        }

    class Meta:
        model = LinkGroup
        fields = (
            'id',
            'name',
            'base_url',
            'status',
            'user',
            'created_at',
            'csv',
            'total_links',
            'total_clicks',
            'unique_clicks',
            'click_rate',
        )


class LinkGroupCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LinkGroup
        fields = ('name', 'base_url', 'domain', 'max_links', 'broadcast', 'network')


class LinkGroupEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = LinkGroup
        fields = ('name', 'total_links')


class LanderDataSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    data = serializers.JSONField()


class LeadgenLeadValidateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadgenLead
        exclude = ('uuid', 'referer')


class LeadgenLeadListSerializer(FlexFieldsModelSerializer):
    user = AccountUserSerializer(read_only=True, allow_null=True)
    account = AccountSimpleSerializer(read_only=True, allow_null=True)
    country = CountrySerializer(read_only=True, allow_null=True)

    class Meta:
        model = LeadgenLead
        exclude = ('uuid', 'referer')


class LeadgenLeadPostbackSerializer(serializers.Serializer):
    lead_id = serializers.UUIDField()
    campaign_id = serializers.CharField(max_length=16)
    device_type = serializers.CharField(max_length=4, required=False)
    device_brand = serializers.CharField(max_length=128, required=False)
    device_model = serializers.CharField(max_length=128, required=False)
    country = serializers.CharField(max_length=2, required=False)
    city = serializers.CharField(max_length=128, required=False)
    region = serializers.CharField(max_length=256, required=False)
    isp = serializers.CharField(max_length=256, required=False)
    connection_type = serializers.CharField(max_length=2, required=False)
    ip = serializers.IPAddressField(required=False)
    browser_name = serializers.CharField(max_length=512, required=False)
    offer_name = serializers.CharField(max_length=512, required=False)
    language = serializers.CharField(max_length=6, required=False)
    payout = serializers.DecimalField(decimal_places=6, max_digits=16, required=False)
