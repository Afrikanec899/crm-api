from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.models.contacts import Contact


class ContactListSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Contact
        exclude = ('referer',)


class ContactCreateSerializer(serializers.ModelSerializer):
    visit_id = serializers.UUIDField(allow_null=True, required=False)

    def validate(self, attrs):
        validated = super(ContactCreateSerializer, self).validate(attrs)
        if not validated.get('phone') and not validated.get('email'):
            raise ValidationError('Phone or Email is required')
        return validated

    class Meta:
        model = Contact
        exclude = ('referer',)


class ContactLeadPostbackSerializer(serializers.Serializer):
    visit_id = serializers.UUIDField()
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
    offer_name = serializers.CharField(max_length=512, required=False, allow_null=True, allow_blank=True)
    language = serializers.CharField(max_length=6, required=False)
    payout = serializers.DecimalField(decimal_places=6, max_digits=16, required=False)


class ContactAnswersSerializer(serializers.ModelSerializer):
    visit_id = serializers.UUIDField()

    class Meta:
        model = Contact
        fields = ('visit_id', 'offer', 'answers', 'device_data', 'country', 'geo_data', 'network')
