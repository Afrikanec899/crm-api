import logging
from typing import Any, Dict, List, Type

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from django_filters import rest_framework as filters
from drf_yasg.utils import swagger_auto_schema
from facebook_business import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount as FBAdAccount
from facebook_business.exceptions import FacebookRequestError
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import UpdateAPIView
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from api.v1.decorators import openapi_ready
from api.v1.filters import AdAccountFilter
from api.v1.serializers.adaccounts import (
    AdAccountAdminSerializer,
    AdAccountCreateRuleSerializer,
    AdAccountEditSerializer,
    AdAccountStartStopSerializer,
    AdAccountUserSerializer,
)
from api.v1.views.core import DinamicFieldsListAPIView
from core.models.core import Account, AdAccount, Rule, User
from core.utils import EXPAND_PARAM, FIELDS_PARAM, OMIT_PARAM

logger = logging.getLogger('django.request')


# TODO сделать нормально
class AdAccountsListView(APIView):
    allowed_roles = (
        User.ADMIN,
        User.FINANCIER,
        User.FARMER,
        User.SETUPER,
        User.MEDIABUYER,
        User.JUNIOR,
        User.MANAGER,
        User.TEAMLEAD,
    )

    @swagger_auto_schema(manual_parameters=[FIELDS_PARAM, EXPAND_PARAM, OMIT_PARAM])
    def get(self, request, *args, **kwargs):
        adaccount_serializer_class = AdAccountUserSerializer
        if request.user.role in [User.ADMIN, User.FINANCIER]:
            adaccount_serializer_class = AdAccountAdminSerializer
        account = get_object_or_404(Account, pk=kwargs['pk'])
        # FIXME: ???
        if account.manager != request.user and request.user.role not in [
            User.ADMIN,
            User.FINANCIER,
            User.SETUPER,
            User.MANAGER,
            User.TEAMLEAD,
        ]:
            if request.user.role == User.TEAMLEAD:
                if account.manager.team != request.user.team and account.manager != request.user:
                    return Response(status=status.HTTP_403_FORBIDDEN)
            else:
                return Response(status=status.HTTP_403_FORBIDDEN)

        adaccounts = AdAccount.objects.filter(account=account).prefetch_related('business').order_by('status')
        data: Dict[int, Dict[str, Any]] = {}
        personal_adaccounts: List[Dict[str, Any]] = []
        adaccounts_businesses = set()
        context = {'request': self.request, 'view': self}
        for adaccount in adaccounts:
            if adaccount.business_id:
                adaccounts_businesses.add(adaccount.business_id)
                if adaccount.business_id not in data:
                    data[adaccount.business_id] = {
                        'name': adaccount.business.name,
                        'id': adaccount.business_id,
                        'is_deleted': True if adaccount.business.deleted_at else False,
                        'business_id': adaccount.business.business_id,
                        # 'share_url': adaccount.business.share_url,
                        'adaccounts': [],
                    }
                data[adaccount.business_id]['adaccounts'].append(
                    adaccount_serializer_class(adaccount, context=context).data
                )
            else:
                personal_adaccounts.append(adaccount_serializer_class(adaccount, context=context).data)

        # Бизнесы без адаккаунтов
        businesses = account.businesses.all().exclude(id__in=list(adaccounts_businesses))
        for business in businesses:
            if business.id not in data:
                data[business.id] = {
                    'name': business.name,
                    'id': business.id,
                    'business_id': business.business_id,
                    # 'share_url': business.share_url,
                    'is_deleted': True if business.deleted_at else False,
                    'adaccounts': [],
                }

        adaccounts_data = list(data.values())
        if personal_adaccounts:
            personal_data = {'name': 'Personal', 'id': None, 'adaccounts': personal_adaccounts}
            adaccounts_data.insert(0, personal_data)

        return Response(data=adaccounts_data)


class AdAccountEditView(UpdateAPIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.JUNIOR, User.TEAMLEAD)
    serializer_class = AdAccountEditSerializer
    queryset = AdAccount.objects.all()

    @openapi_ready
    def get_queryset(self) -> QuerySet:
        qs = super(AdAccountEditView, self).get_queryset()
        self.account = get_object_or_404(Account, pk=self.kwargs['account_id'])
        if self.account.manager == self.request.user:
            qs = qs.filter(account=self.account)
        else:
            if self.request.user.role == User.ADMIN:
                qs = qs.filter(account=self.account)

            elif self.request.user.role == User.TEAMLEAD:
                if (
                    self.account.manager
                    and self.account.manager.team
                    and self.request.user.team == self.account.manager.team
                ):
                    qs = qs.filter(account=self.account)
                else:
                    return AdAccount.objects.none()
            else:
                return AdAccount.objects.none()
        # qs = qs.filter(account=self.account)
        return qs

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        AdAccount.update(pk=instance.pk, updated_by=request.user, action_verb='updated', **serializer.validated_data)
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}
        data = {'account': self.account.id, 'has_campaign': self.account.has_campaign}
        return Response(data=data, status=status.HTTP_200_OK)


class AdAccountsView(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.JUNIOR, User.TEAMLEAD, User.FINANCIER, User.MANAGER)
    queryset = AdAccount.objects.filter()
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = AdAccountFilter

    def get_serializer_class(self) -> Type[BaseSerializer]:
        if self.request.user.role in [User.ADMIN, User.FINANCIER]:
            return AdAccountAdminSerializer
        return AdAccountUserSerializer

    def get_queryset(self) -> QuerySet:
        queryset = super(AdAccountsView, self).get_queryset()
        if self.request.user.role in [User.MEDIABUYER, User.JUNIOR]:
            return queryset.filter(account__manager=self.request.user)
        return queryset


class AdAccountStartStopCampaings(APIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.JUNIOR, User.MANAGER, User.TEAMLEAD)

    @swagger_auto_schema(request_body=AdAccountStartStopSerializer)
    def post(self, request, *args, **kwargs):
        adaccount_obj = get_object_or_404(AdAccount, id=request.data['adaccount_id'])

        if not adaccount_obj.account.fb_access_token:
            return Response(data={'error': 'Add account token before'}, status=status.HTTP_400_BAD_REQUEST)

        FacebookAdsApi.init(
            access_token=adaccount_obj.account.fb_access_token, proxies=adaccount_obj.account.proxy_config
        )
        adaccount = FBAdAccount(fbid=f'act_{adaccount_obj.adaccount_id}')

        params = {'status': 'PAUSED'}

        if kwargs['action'] == 'start':
            params = {'status': 'ACTIVE'}

        try:
            campaigns = adaccount.get_campaigns()
            for campaign in campaigns:
                campaign.api_update(params=params)

        except FacebookRequestError as e:
            logger.error(e, exc_info=True)
            return Response(
                data={'error': e.body()['error'].get('error_user_msg') or e.body()['error'].get('message')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(data={'error': 'Unknown error'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_200_OK)


# TODO: validate
class AdAccountCreateRule(APIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.JUNIOR, User.MANAGER, User.TEAMLEAD)

    @swagger_auto_schema(request_body=AdAccountCreateRuleSerializer)
    def post(self, request, *args, **kwargs):
        adaccount_obj = get_object_or_404(AdAccount, id=kwargs['pk'])

        if not adaccount_obj.account.fb_access_token:
            return Response(data={'error': 'Add account token before'}, status=status.HTTP_400_BAD_REQUEST)

        FacebookAdsApi.init(
            access_token=adaccount_obj.account.fb_access_token, proxies=adaccount_obj.account.proxy_config
        )
        adaccount = FBAdAccount(fbid=f'act_{adaccount_obj.adaccount_id}')

        rules = Rule.objects.filter(id__in=request.data['rules'])
        if not rules.exists():
            return Response(status=status.HTTP_400_BAD_REQUEST)
        for rule in rules:
            decimal_data = [
                'spent',
                # 'result',
                'cost_per',
                'cpm',
                'cost_per_link_click',
                'cost_per_initiate_checkout_fb',
                'link_ctr',
            ]
            for filter in rule.evaluation_spec['filters']:
                if filter['field'] in decimal_data:
                    if not isinstance(filter['value'], list):
                        value = filter['value'].replace(',', '.')
                        filter['value'] = float(value) * 100

            rule.evaluation_spec['filters'].append(
                {"field": "attribution_window", "value": "1D_VIEW_1D_CLICK", "operator": "EQUAL"}
            )

            params = {
                'evaluation_spec': rule.evaluation_spec,
                'execution_spec': rule.execution_spec,
                'name': rule.name,
                'schedule_spec': rule.schedule_spec,
            }
            try:
                adaccount.create_ad_rules_library(params=params)
            except FacebookRequestError as e:
                logger.error(e, exc_info=True)
                return Response(
                    data={'error': e.body()['error'].get('error_user_msg') or e.body()['error'].get('message')},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.error(e, exc_info=True)
                return Response(data={'error': 'Unknown error'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_200_OK)
