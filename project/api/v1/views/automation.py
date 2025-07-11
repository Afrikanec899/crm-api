from typing import Any

from django.db.models import QuerySet
from django.db.models.query_utils import Q
from django.utils.datastructures import MultiValueDictKeyError

from django_filters import rest_framework as filters
from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins, status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import CreateAPIView, GenericAPIView, get_object_or_404
from rest_framework.parsers import FileUploadParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from api.v1.filters import AdsCreateTaskLogFilter, LeadgenFilter, RuleFilter, TemplateFilter
from api.v1.serializers.automation import (
    AdsCreateLogListSerializer,
    AdsCreateTaskCreateSerializer,
    ImageSerializer,
    LeadgenSerializer,
    MediaSerializer,
    RuleSerializer,
    TemplateSerializer,
    VideoSerializer,
)
from api.v1.views.core import DinamicFieldsListAPIView, DinamicFieldsRetrieveAPIView
from core.models.core import AdsCreateTask, CampaignTemplate, Leadgen, Rule, UploadedImage, UploadedVideo, User
from core.utils import EXPAND_PARAM, FIELDS_PARAM, OMIT_PARAM


class TemplatesViewSet(ModelViewSet):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.JUNIOR, User.MANAGER, User.TEAMLEAD)
    queryset = CampaignTemplate.objects.all().prefetch_related('user')
    serializer_class = TemplateSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = TemplateFilter

    def get_queryset(self) -> QuerySet:
        queryset = super(TemplatesViewSet, self).get_queryset()
        if self.request.user.role in [User.MEDIABUYER, User.MANAGER, User.JUNIOR]:  # FIXME
            return queryset.filter(Q(user=self.request.user) | Q(user__isnull=True))
        elif self.request.user.role == User.TEAMLEAD:
            return queryset.filter(
                Q(user__team=self.request.user.team, user__team__isnull=False) | Q(user__isnull=True)
            )
        return queryset

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(user=self.request.user)


class TemplateCopyView(APIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.JUNIOR, User.MANAGER, User.TEAMLEAD)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        template = CampaignTemplate.objects.filter(id=kwargs['pk']).first()
        if self.request.user.role in [User.MEDIABUYER, User.MANAGER, User.JUNIOR]:
            if template.user != self.request.user:
                return Response(status=status.HTTP_404_NOT_FOUND)
        elif self.request.user.role == User.TEAMLEAD:
            if template.user.team != self.request.user.team:
                return Response(status=status.HTTP_404_NOT_FOUND)

        template.id = None
        template.user = request.user
        template.name = f'{template.name} copy'
        template.save()
        return Response(status=status.HTTP_201_CREATED)


class AdsCreateView(CreateAPIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR)
    queryset = AdsCreateTask.objects.all()
    serializer_class = AdsCreateTaskCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # headers = self.get_success_headers(serializer.data)
        return Response(status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        # print(serializer.validated_data['adaccounts'][0].data)
        AdsCreateTask.create_many(
            self.request.user,
            template=serializer.validated_data['template'],
            adaccounts=serializer.validated_data['adaccounts'],
        )


class AdsRecreateView(APIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR)
    queryset = AdsCreateTask.objects.all()

    def post(self, request, *args, **kwargs):
        ads_task = get_object_or_404(AdsCreateTask, pk=self.kwargs['pk'])

        if ads_task.user != request.user:
            if request.user.role not in [User.ADMIN, User.TEAMLEAD]:
                raise PermissionError()

            elif request.user.role == User.TEAMLEAD and ads_task.user.team and ads_task.user.team != request.user.team:
                raise PermissionError()

        ads_task.remote_create()

        return Response(status=status.HTTP_200_OK)


class BaseAdsLogView(GenericAPIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR)
    queryset = AdsCreateTask.objects.all().prefetch_related('user')
    serializer_class = AdsCreateLogListSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = AdsCreateTaskLogFilter

    def get_queryset(self) -> QuerySet:
        queryset = super(BaseAdsLogView, self).get_queryset()
        if self.request.user.role in [User.MEDIABUYER, User.MANAGER, User.JUNIOR]:
            return queryset.filter(user=self.request.user)
        elif self.request.user.role == User.TEAMLEAD:
            return queryset.filter(
                Q(user__team__isnull=False, user__team=self.request.user.team) | Q(user=self.request.user)
            )
        return queryset


class AdsCreateLogListView(BaseAdsLogView, DinamicFieldsListAPIView):
    pass


class AdsCreateLogRetrieveView(BaseAdsLogView, DinamicFieldsRetrieveAPIView):
    pass


# TODO: Сделать чтобы в схеме были поля
class RulesViewSet(ModelViewSet):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR)
    queryset = Rule.objects.all()
    serializer_class = RuleSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = RuleFilter

    @swagger_auto_schema(manual_parameters=[FIELDS_PARAM, EXPAND_PARAM, OMIT_PARAM])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet:
        queryset = super(RulesViewSet, self).get_queryset()
        if self.request.user.role in [User.MEDIABUYER, User.MANAGER, User.JUNIOR]:
            return queryset.filter(Q(user=self.request.user) | Q(user__isnull=True))

        elif self.request.user.role == User.TEAMLEAD:
            return queryset.filter(
                Q(user__team=self.request.user.team, user__team__isnull=False)
                | Q(user__isnull=True)
                | Q(user=self.request.user)
            )

        return queryset

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(user=self.request.user)


class LeadgenViewSet(ModelViewSet):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR)
    queryset = Leadgen.objects.all()
    serializer_class = LeadgenSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = LeadgenFilter

    @swagger_auto_schema(manual_parameters=[FIELDS_PARAM, EXPAND_PARAM, OMIT_PARAM])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet:
        queryset = super(LeadgenViewSet, self).get_queryset()
        if self.request.user.role != User.ADMIN:
            return queryset.filter(
                Q(user=self.request.user)
                | Q(user__isnull=True)
                | Q(user__team=self.request.user.team, user__team__isnull=False)
            )
        #
        # elif self.request.user.role == User.TEAMLEAD:
        #     return queryset.filter(
        #         Q(user__team=self.request.user.team, user__team__isnull=False)
        #         | Q(user__isnull=True)
        #         | Q(user=self.request.user)
        #     )

        return queryset

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(user=self.request.user)


class LeadgenCopyView(APIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        leadgen = Leadgen.objects.filter(id=kwargs['pk']).first()
        if self.request.user.role in [User.MEDIABUYER, User.MANAGER, User.JUNIOR]:
            if leadgen.user != self.request.user and (
                leadgen.user.team is not None and leadgen.user.team != self.request.user.team
            ):
                return Response(status=status.HTTP_404_NOT_FOUND)
        elif self.request.user.role == User.TEAMLEAD:
            if leadgen.user.team != self.request.user.team:
                return Response(status=status.HTTP_404_NOT_FOUND)

        leadgen.id = None
        leadgen.user = request.user
        leadgen.save()
        return Response(status=status.HTTP_201_CREATED)


class ImagesListView(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, GenericViewSet):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR, User.FARMER)
    queryset = UploadedImage.objects.all()
    serializer_class = ImageSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)

    def get_queryset(self) -> QuerySet:
        queryset = super(ImagesListView, self).get_queryset()
        if self.request.user.role in [User.MEDIABUYER, User.JUNIOR, User.FARMER]:
            return queryset.filter(user=self.request.user)

        elif self.request.user.role == User.TEAMLEAD:
            return queryset.filter(
                Q(user__team=self.request.user.team, user__team__isnull=False) | Q(user=self.request.user)
            )

        return queryset


class ImageUploadView(APIView):
    """
    Api endpoint for upload image
    """

    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR, User.FARMER)
    parser_classes = (FileUploadParser,)

    @swagger_auto_schema(request_body=MediaSerializer)
    def post(self, request, **kwargs):
        try:
            uploaded_file = request.data.get("file")
        except MultiValueDictKeyError:
            raise MultiValueDictKeyError("Upload a file with the key 'file'")

        serializer = ImageSerializer(data={"file": uploaded_file})
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)

        return Response(serializer.data, status=status.HTTP_200_OK)


class VideoListView(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, GenericViewSet):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR, User.FARMER)
    queryset = UploadedVideo.objects.all()
    serializer_class = VideoSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)

    def get_queryset(self) -> QuerySet:
        queryset = super(VideoListView, self).get_queryset()
        if self.request.user.role in [User.MEDIABUYER, User.JUNIOR, User.FARMER]:
            return queryset.filter(user=self.request.user)

        elif self.request.user.role == User.TEAMLEAD:
            return queryset.filter(
                Q(user__team=self.request.user.team, user__team__isnull=False) | Q(user=self.request.user)
            )
        return queryset


class VideoUploadView(APIView):
    """
    Api endpoint for upload video
    """

    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD, User.JUNIOR, User.FARMER)
    parser_classes = (FileUploadParser,)

    @swagger_auto_schema(request_body=VideoSerializer)
    def post(self, request, **kwargs):
        try:
            uploaded_file = request.data.get("file")
        except MultiValueDictKeyError:
            raise MultiValueDictKeyError("Upload a file with the key 'file'")

        serializer = VideoSerializer(data={"file": uploaded_file})
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)

        return Response(serializer.data, status=status.HTTP_200_OK)
