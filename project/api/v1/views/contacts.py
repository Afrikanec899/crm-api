import logging

from django_filters import rest_framework as filters
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.filters import ContactFilter
from api.v1.serializers.contacts import (
    ContactAnswersSerializer,
    ContactCreateSerializer,
    ContactLeadPostbackSerializer,
    ContactListSerializer,
)
from api.v1.views.core import DinamicFieldsListAPIView
from core.models import Contact, User
from core.tasks.contacts import process_contact_postback_task, process_contact_task

logger = logging.getLogger(__name__)


class ContactViewSet(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = Contact.objects.all()
    serializer_class = ContactListSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = ContactFilter


class ContactCreateView(APIView):
    permission_classes = ()

    def post(self, request, *args, **kwargs):
        serializer = ContactCreateSerializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        contact_data = {'referer': self.request.META.get('HTTP_REFERER'), **serializer.validated_data}
        process_contact_task.delay(contact_data)
        return Response(status=status.HTTP_201_CREATED)


class ContactAnswersCreateView(APIView):
    permission_classes = ()

    def post(self, request, *args, **kwargs):
        serializer = ContactAnswersSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        contact_data = {'referer': self.request.META.get('HTTP_REFERER'), **serializer.validated_data}
        process_contact_task.delay(contact_data)
        return Response(status=status.HTTP_201_CREATED)


class ContactPostbackView(APIView):
    permission_classes = ()

    def get(self, request, **kwargs):
        serializer = ContactLeadPostbackSerializer(data=request.GET)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(status=status.HTTP_200_OK)

        contact_data = {**serializer.validated_data}
        process_contact_postback_task.delay(contact_data)

        return Response(status=status.HTTP_200_OK)
