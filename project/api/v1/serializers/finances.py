from decimal import Decimal

from creditcards.validators import CCNumberValidator, CSCValidator
from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import empty

from api.v1.serializers.adaccounts import AdAccountSimpleSerializer
from core.models.core import AdAccount, AdAccountCreditCard, AdAccountTransaction, Card, FinAccount


class AdAccountCreditCardListSerializer(FlexFieldsModelSerializer):
    card_id = serializers.IntegerField(source='card.id', read_only=True)
    number = serializers.CharField(source='card.number', read_only=True)
    comment = serializers.CharField(source='card.comment', read_only=True, default='')
    funds = serializers.DecimalField(
        source='card.funds', read_only=True, default=Decimal('0.00'), max_digits=10, decimal_places=2
    )
    fb_spends = serializers.DecimalField(
        source='card.fb_spends', read_only=True, default=Decimal('0.00'), max_digits=10, decimal_places=2
    )
    is_active = serializers.BooleanField(source='card.is_active', read_only=True, default=True)
    adaccount = AdAccountSimpleSerializer(read_only=True)

    class Meta:
        model = AdAccountCreditCard
        fields = (
            'id',
            'number',
            'comment',
            'funds',
            'fb_spends',
            'is_active',
            'created_at',
            'display_string',
            'card_id',
            'adaccount',
        )


class CreditCardCreateSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=16, write_only=True, validators=[CCNumberValidator()])
    exp_month = serializers.CharField(max_length=2)
    exp_year = serializers.CharField(max_length=2)
    cvv = serializers.CharField(validators=[CSCValidator()])
    initial_balance = serializers.DecimalField(max_digits=10, decimal_places=2, write_only=True, required=False)
    comment = serializers.CharField(max_length=255, write_only=True, required=False, allow_blank=True)


class AdaccountCreditCardEditSerializer(serializers.Serializer):
    spend = serializers.DecimalField(max_digits=10, decimal_places=2, write_only=True, required=False)
    number = serializers.CharField(max_length=16, write_only=True, required=False)
    initial_balance = serializers.DecimalField(max_digits=10, decimal_places=2, write_only=True, required=False)
    comment = serializers.CharField(max_length=255, write_only=True, required=False, allow_blank=True)
    is_active = serializers.BooleanField(write_only=True, required=False, default=True)

    def __init__(self, instance=None, data=empty, **kwargs):
        self.adaccount_card = kwargs.pop('adaccount_card', None)
        super(AdaccountCreditCardEditSerializer, self).__init__(instance, data, **kwargs)

    def validate_number(self, number):
        _, card_type_title = Card.get_type_by_number(number)
        # display_string = f'{card_type_title}*{number[-4:]}'
        if (
            self.adaccount_card.display_string[: len(card_type_title)] != card_type_title
            and self.adaccount_card.display_string[-4:] != number[-4:]
        ):
            # if display_string != self.adaccount_card.display_string:
            raise ValidationError('Card number invalid!')
        return number


class CreditCardDetailSerializer(FlexFieldsModelSerializer):
    display_string = serializers.CharField(read_only=True)
    adaccounts = serializers.SerializerMethodField(read_only=True)

    def get_adaccounts(self, obj):
        card_adaccounts = AdAccountCreditCard.objects.filter(card=obj)
        if card_adaccounts.exists():
            adaccount_ids = card_adaccounts.values_list('adaccount_id', flat=True)
            adaccounts = AdAccount.objects.filter(id__in=list(adaccount_ids))
            return AdAccountSimpleSerializer(adaccounts, many=True).data
        return {}

    class Meta:
        model = Card
        fields = (
            'id',
            'number',
            'comment',
            'funds',
            'display_string',
            'is_active',
            'created_at',
            'adaccounts',
            'fb_spends',
            'spend',
        )


class CreditCardEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = (
            'id',
            'number',
            'comment',
            'is_active',
            'spend',
        )


class TransactionSerializer(FlexFieldsModelSerializer):
    adaccount = AdAccountSimpleSerializer(read_only=True)
    card = serializers.SerializerMethodField(read_only=True)

    def get_card(self, obj):
        if obj.card:
            return {'id': obj.card_id, 'display_string': obj.card.display_string}
        return {}

    class Meta:
        model = AdAccountTransaction
        exclude = ('data',)


class FinAccountSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = FinAccount
        exclude = ('data',)


class FinAccountCreateEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinAccount
        exclude = ('created_at', 'created_by', 'updated_at', 'slug')
