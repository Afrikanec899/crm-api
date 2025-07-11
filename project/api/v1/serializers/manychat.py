from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.models.contacts import Contact


# Manychat Validate data serializer
class ManyChatBaseSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=255)
    userid = serializers.IntegerField()


class ManychatPostbackSerializer(serializers.Serializer):
    var1 = serializers.IntegerField()
    var2 = serializers.IntegerField()


class ManyChatMatchingSerializer(ManyChatBaseSerializer):
    pageid = serializers.IntegerField()


class SaveTokenDataSerializer(ManyChatBaseSerializer):
    pageid = serializers.IntegerField()
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_null=True, allow_blank=True)


class ManyChatDateMessageSerializer(ManyChatBaseSerializer):
    text = serializers.CharField()
    timeadd = serializers.IntegerField()


class ManyChatImageMessageSerializer(ManyChatBaseSerializer):
    text = serializers.CharField()
    name1 = serializers.CharField()
    name2 = serializers.CharField()
