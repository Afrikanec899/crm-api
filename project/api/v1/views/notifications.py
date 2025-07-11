from collections import OrderedDict

from django.utils import timezone

from django_filters import rest_framework as filters
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.filters import NotificationFilter
from api.v1.serializers.notifications import NotificationListSerializer, NotificationReadSerializer
from core.models.core import Notification


class NotificationPagination(LimitOffsetPagination):
    def paginate_queryset(self, queryset, request, view=None):
        self.count = self.get_count(queryset)
        self.unread_count = self.get_unread_count(queryset)
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None

        self.offset = self.get_offset(request)
        self.request = request
        if self.count > self.limit and self.template is not None:
            self.display_page_controls = True

        if self.count == 0 or self.offset > self.count:
            return []
        offset = self.offset
        limit = self.offset + self.limit
        return list(queryset[offset:limit])

    def get_unread_count(self, queryset):
        queryset = queryset.filter(readed_at__isnull=True)
        try:
            return queryset.count()
        except (AttributeError, TypeError):
            return len(queryset)

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ('count', self.count),
                    ('unread', self.unread_count),
                    ('next', self.get_next_link()),
                    ('previous', self.get_previous_link()),
                    ('results', data),
                ]
            )
        )


class NotificationsListView(ListAPIView):
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = NotificationFilter
    serializer_class = NotificationListSerializer
    queryset = Notification.objects.all()
    pagination_class = NotificationPagination

    def get_queryset(self):
        qs = super(NotificationsListView, self).get_queryset()
        qs = qs.filter(recipient=self.request.user)
        return qs


class NotificationsListReadView(APIView):
    http_method_names = ['patch']

    def patch(self, request, *args, **kwargs):
        update_data = request.data
        now = timezone.now()

        if isinstance(update_data, dict):
            if update_data.get('read_all') and update_data.get('id'):
                Notification.objects.filter(id__lte=update_data['id'], recipient=request.user).update(readed_at=now)

        if isinstance(update_data, list):
            update_list = update_data

            serializer = NotificationReadSerializer(data=update_list, many=True)
            serializer.is_valid(raise_exception=True)

            notify_ids = [x['id'] for x in serializer.validated_data]
            Notification.objects.filter(id__in=notify_ids, recipient=request.user).update(readed_at=now)
        return Response(status=status.HTTP_200_OK)
