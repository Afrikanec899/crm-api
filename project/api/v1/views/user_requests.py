from typing import Any, Dict

from django.db.models import Q

from django_filters import rest_framework as filters
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import CreateAPIView, GenericAPIView, UpdateAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from api.v1.filters import RequestsFilter
from api.v1.permissions import AllowedRoles, IsOwnerOrAdminRoles
from api.v1.serializers.user_requests import (
    UserRequestCreateSerializer,
    UserRequestListAdminSerializer,
    UserRequestListManagerSerializer,
    UserRequestListMediabuyerSerializer,
    UserRequestListSetuperSerializer,
    UserRequestListTeamleadSerializer,
    UserRequestUpdateSerializer,
)
from api.v1.views.core import DinamicFieldsListAPIView
from core.models.core import Account, User, UserRequest


class BaseRequestView(GenericAPIView):
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = RequestsFilter
    queryset = UserRequest.objects.all().prefetch_related('user').prefetch_related('processed_by')
    serializers: Dict[int, Any] = {}
    request_type = None

    def get_queryset(self):
        assert self.request_type, "'%s' should include a `request_type` attribute," % self.__class__.__name__
        qs = super(BaseRequestView, self).get_queryset()
        qs = qs.filter(request_type=self.request_type)
        if self.request.user.role not in [
            User.ADMIN,
            User.FINANCIER,
            User.SETUPER,
            User.TEAMLEAD,
            User.SUPPLIER,
            User.SUPPLIER_TEAMLEAD,
            User.MANAGER,
        ]:
            return qs.filter(user=self.request.user)
        # TODO: TEAMLEAD
        elif self.request.user.role == User.TEAMLEAD:
            return qs.filter(
                Q(user=self.request.user) | Q(user__team=self.request.user.team, user__team__isnull=False)
            )
        else:
            return qs

    def get_serializer_class(self):
        assert self.serializers, "'%s' should either include a `serializers` attribute," % self.__class__.__name__
        return self.serializers[self.request.user.role]

    def get_serializer(self, *args: Any, **kwargs: Any) -> BaseSerializer:
        """
        Return the serializer instance that should be used for validating and
        deserializing input, and for serializing output.
        """
        serializer_class = self.get_serializer_class()
        kwargs['context'] = self.get_serializer_context()
        kwargs['user'] = self.request.user
        return serializer_class(*args, **kwargs)


class RequestsMoneyListView(BaseRequestView, DinamicFieldsListAPIView):
    allowed_roles = (
        User.ADMIN,
        User.FINANCIER,
        User.MEDIABUYER,
        User.JUNIOR,
        User.MANAGER,
        User.TEAMLEAD,
        User.FARMER,
    )
    serializers = {
        User.ADMIN: UserRequestListAdminSerializer,
        User.FINANCIER: UserRequestListAdminSerializer,
        User.MEDIABUYER: UserRequestListMediabuyerSerializer,
        User.JUNIOR: UserRequestListMediabuyerSerializer,
        User.FARMER: UserRequestListMediabuyerSerializer,
        User.MANAGER: UserRequestListManagerSerializer,
        User.TEAMLEAD: UserRequestListTeamleadSerializer,
    }
    request_type = UserRequest.MONEY


class RequestsAccountListView(BaseRequestView, DinamicFieldsListAPIView):
    allowed_roles = (
        User.ADMIN,
        User.MEDIABUYER,
        User.JUNIOR,
        User.MANAGER,
        User.TEAMLEAD,
        User.FARMER,
    )
    serializers = {
        User.ADMIN: UserRequestListAdminSerializer,
        User.MEDIABUYER: UserRequestListMediabuyerSerializer,
        User.JUNIOR: UserRequestListMediabuyerSerializer,
        User.FARMER: UserRequestListMediabuyerSerializer,
        User.MANAGER: UserRequestListSetuperSerializer,
        User.TEAMLEAD: UserRequestListTeamleadSerializer,
    }
    request_type = UserRequest.ACCOUNTS


class RequestsFixListView(BaseRequestView, DinamicFieldsListAPIView):
    allowed_roles = (
        User.ADMIN,
        User.MEDIABUYER,
        User.JUNIOR,
        User.MANAGER,
        User.TEAMLEAD,
        User.SUPPLIER,
        User.SUPPLIER_TEAMLEAD,
        User.FINANCIER,
        User.FARMER,
    )
    serializers = {
        User.ADMIN: UserRequestListAdminSerializer,
        User.MEDIABUYER: UserRequestListMediabuyerSerializer,
        User.JUNIOR: UserRequestListMediabuyerSerializer,
        User.FARMER: UserRequestListMediabuyerSerializer,
        User.MANAGER: UserRequestListSetuperSerializer,
        User.TEAMLEAD: UserRequestListTeamleadSerializer,
        User.SUPPLIER: UserRequestListSetuperSerializer,
        User.SUPPLIER_TEAMLEAD: UserRequestListSetuperSerializer,
        User.FINANCIER: UserRequestListAdminSerializer,
    }
    request_type = UserRequest.FIX

    def get_queryset(self):
        qs = super(RequestsFixListView, self).get_queryset()
        # TODO: TEAMLEAD
        if self.request.user.role == User.SUPPLIER:
            supplier_accounts = Account.objects.filter(supplier=self.request.user).values_list('id', flat=True)
            return qs.filter(request_data__category='docs', request_data__account_id__in=list(supplier_accounts))

        elif self.request.user.role == User.SUPPLIER_TEAMLEAD:
            supplier_accounts = Account.objects.filter(supplier__team=self.request.user.team).values_list(
                'id', flat=True
            )
            return qs.filter(request_data__category='docs', request_data__account_id__in=list(supplier_accounts))

        elif self.request.user.role == User.MANAGER:
            return qs.filter(
                Q(user=self.request.user, request_data__category='finances') | Q(request_data__category='docs')
            )

        elif self.request.user.role == User.FINANCIER:
            return qs.filter(
                Q(request_data__category='finances') | Q(request_data__category__isnull=True)  # для совместимости
            )
        else:
            return qs


class RequestsSetupListView(BaseRequestView, DinamicFieldsListAPIView):
    allowed_roles = (
        User.ADMIN,
        User.MEDIABUYER,
        User.JUNIOR,
        User.MANAGER,
        User.TEAMLEAD,
        User.SETUPER,
        User.FARMER,
    )
    serializers = {
        User.ADMIN: UserRequestListAdminSerializer,
        User.MEDIABUYER: UserRequestListMediabuyerSerializer,
        User.JUNIOR: UserRequestListMediabuyerSerializer,
        User.FARMER: UserRequestListMediabuyerSerializer,
        User.MANAGER: UserRequestListSetuperSerializer,
        User.TEAMLEAD: UserRequestListTeamleadSerializer,
        User.SETUPER: UserRequestListSetuperSerializer,
    }
    request_type = UserRequest.SETUP


class RequestCreateView(CreateAPIView):
    serializer_class = UserRequestCreateSerializer
    queryset = UserRequest.objects.all()

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(user=self.request.user, data=request.data)
        serializer.is_valid(raise_exception=True)

        UserRequest.create(user=request.user, **serializer.validated_data)
        return Response(status=status.HTTP_201_CREATED)


# TODO: Refactor && permissions
class RequestUpdateView(UpdateAPIView):
    allowed_roles = (
        User.ADMIN,
        User.FINANCIER,
        User.SETUPER,
        User.MEDIABUYER,
        User.JUNIOR,
        User.FARMER,
        User.MANAGER,
        User.TEAMLEAD,
        User.SUPPLIER,
        User.SUPPLIER_TEAMLEAD,
    )
    admin_roles = (
        User.ADMIN,
        User.FINANCIER,
        User.SETUPER,
        User.MANAGER,
        User.TEAMLEAD,
        User.SUPPLIER,
        User.SUPPLIER_TEAMLEAD,
        User.FARMER,
    )
    permission_classes = (IsOwnerOrAdminRoles, AllowedRoles)
    serializer_class = UserRequestUpdateSerializer
    queryset = UserRequest.objects.all()

    def get_object(self) -> Any:
        obj = super(RequestUpdateView, self).get_object()
        request_type = obj.request_type

        if request_type in ['money', 'fix']:
            # TODO: TEAMLEAD
            if self.request.user.role not in [
                User.ADMIN,
                User.FINANCIER,
                User.TEAMLEAD,
                User.SUPPLIER,
                User.SUPPLIER_TEAMLEAD,
            ]:
                if obj.user != self.request.user:
                    raise PermissionError()

            elif self.request.user.role in [User.TEAMLEAD]:
                if obj.user.team and obj.user.team != self.request.user.team and obj.user != self.request.user:
                    raise PermissionError()

        elif request_type == 'setup':
            if self.request.user.role not in [User.ADMIN, User.FINANCIER, User.SETUPER, User.TEAMLEAD]:
                if obj.user != self.request.user:
                    raise PermissionError()

            elif self.request.user.role == User.TEAMLEAD:
                if obj.user.team and obj.user.team != self.request.user.team and obj.user != self.request.user:
                    raise PermissionError()

        elif request_type == 'accounts':
            if self.request.user.role not in [User.ADMIN, User.MANAGER, User.TEAMLEAD]:
                if obj.user != self.request.user:
                    raise PermissionError()

            elif self.request.user.role == User.TEAMLEAD:
                if obj.user.team and obj.user.team != self.request.user.team and obj.user != self.request.user:
                    raise PermissionError()

        return obj

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, user=self.request.user, partial=partial)
        serializer.is_valid(raise_exception=True)
        user_request = UserRequest.update(pk=instance.pk, updated_by=request.user, **serializer.validated_data)
        return Response(self.get_serializer(user_request).data)
