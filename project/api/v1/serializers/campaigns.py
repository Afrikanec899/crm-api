from rest_framework import serializers

from core.models.core import Campaign


class CampaignListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = ('name', 'id')
