from rest_framework import serializers

from core.models.core import Notification


class NotificationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('category', 'level', 'id', 'readed_at', 'data', 'created_at')


class NotificationReadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    readed = serializers.BooleanField()
