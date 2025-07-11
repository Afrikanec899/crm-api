from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers

from api.v1.serializers.accounts import AccountSimpleSerializer
from api.v1.serializers.campaigns import CampaignListSerializer
from core.models.core import AdAccount, AdAccountCreditCard, BusinessManager, Campaign, Rule


class AdAccountBusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessManager
        fields = ('id', 'name')


class AdAccountSimpleSerializer(serializers.ModelSerializer):
    account = AccountSimpleSerializer(read_only=True)
    business = AdAccountBusinessSerializer(read_only=True)

    class Meta:
        model = AdAccount
        fields = (
            'id',
            'name',
            'business',
            'account',
        )


class AdAccountCreditCardSerializer(serializers.ModelSerializer):
    number = serializers.CharField(source='card.number', read_only=True)
    comment = serializers.CharField(source='card.comment', read_only=True)
    is_active = serializers.BooleanField(source='card.is_active', read_only=True)
    card_id = serializers.IntegerField(source='card.id', read_only=True)

    class Meta:
        model = AdAccountCreditCard
        fields = ('id', 'number', 'comment', 'display_string', 'is_active', 'card_id')


class CreditCardSimpleSerializer(serializers.ModelSerializer):
    comment = serializers.CharField(source='card.comment', read_only=True)

    class Meta:
        model = AdAccountCreditCard
        fields = ('id', 'display_string', 'card_id', 'comment')


class AdAccountFinanceSerializer(serializers.ModelSerializer):
    cards = serializers.SerializerMethodField(read_only=True)

    def get_cards(self, obj):
        cards = obj.adaccountcreditcard_set.all()
        if cards.exists():
            # cards_ids = cards.values_list('card_id', flat=True)
            # cards = Card.objects.filter(id__in=list(cards_ids))
            return CreditCardSimpleSerializer(cards, many=True).data
        return []

    class Meta:
        model = AdAccount
        fields = (
            'id',
            'name',
            'cards',
        )


class AdAccountAdminSerializer(FlexFieldsModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    disable_reason_display = serializers.CharField(source='get_disable_reason_display', read_only=True)
    campaign = CampaignListSerializer(read_only=True)
    business = AdAccountBusinessSerializer(read_only=True)
    cards = AdAccountCreditCardSerializer(source='adaccountcreditcard_set', many=True, read_only=True)

    class Meta:
        model = AdAccount
        fields = (
            'id',
            'name',
            'cards',
            'status',
            'status_display',
            'disable_reason_display',
            'created_at',
            'deleted_at',
            'business',
            'amount_spent',
            'payment_cycle',
            'limit',
            'balance',
            'cards_balance',
            'campaign',
            'currency',
            'pixels',
            'timezone_name',
            'timezone_offset_hours_utc',
        )
        read_only_fields = fields


class AdAccountUserSerializer(AdAccountAdminSerializer):
    class Meta(AdAccountAdminSerializer.Meta):
        fields = (
            'id',
            'name',
            'status',
            'status_display',
            'disable_reason_display',
            'created_at',
            'deleted_at',
            'business',
            'amount_spent',
            'payment_cycle',
            'limit',
            'balance',
            'cards_balance',
            'campaign',
            'currency',
            'pixels',
            'timezone_name',
            'timezone_offset_hours_utc',
        )
        read_only_fields = fields


class AdAccountEditSerializer(serializers.ModelSerializer):
    campaign = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Campaign.objects.all(), allow_null=True, allow_empty=True
    )
    # TODO: Валидация владельца кампании

    class Meta:
        model = AdAccount
        fields = ('campaign',)


class AdAccountCreateRuleSerializer(serializers.Serializer):
    rules = serializers.PrimaryKeyRelatedField(write_only=True, queryset=Rule.objects.all(), many=True)


class AdAccountStartStopSerializer(serializers.Serializer):
    adaccount_id = serializers.PrimaryKeyRelatedField(write_only=True, queryset=AdAccount.objects.all(),)
