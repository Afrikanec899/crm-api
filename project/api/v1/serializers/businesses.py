from rest_flex_fields import FlexFieldsModelSerializer

from api.v1.serializers.accounts import AccountSimpleSerializer
from core.models.core import Action, BusinessManagerLog, BusinessShareUrl


class BusinessShareListSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = BusinessShareUrl
        exclude = ('business',)


class BusinessActionSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Action
        fields = ('actor', 'verb', 'action_object_repr', 'target_object_repr', 'timesince', 'data', 'action_datetime')


class BusinessManagerLogSerializer(FlexFieldsModelSerializer):
    account = AccountSimpleSerializer()

    class Meta:
        model = BusinessManagerLog
        fields = ('start_at', 'end_at', 'account')
