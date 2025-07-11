from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.db.models.aggregates import Sum

from django_filters import rest_framework as filters
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import CreateAPIView, UpdateAPIView, get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.filters import CreditCardFilter, TransactionFilter
from api.v1.serializers.finances import (
    AdaccountCreditCardEditSerializer,
    AdAccountCreditCardListSerializer,
    CreditCardCreateSerializer,
    CreditCardDetailSerializer,
    CreditCardEditSerializer,
    FinAccountCreateEditSerializer,
    FinAccountSerializer,
    TransactionSerializer,
)
from api.v1.views.core import DinamicFieldsListAPIView, DinamicFieldsRetrieveAPIView, TotalStatsPagination
from core.models.core import AdAccount, AdAccountCreditCard, AdAccountTransaction, Card, FinAccount, User
from core.tasks.helpers import attach_card, load_adaccount_payment_methods


class AdaccountCardListView(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = AdAccountCreditCard.objects.all()
    serializer_class = AdAccountCreditCardListSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = CreditCardFilter


class CreditCardRetrieveView(DinamicFieldsRetrieveAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = Card.objects.all()
    serializer_class = CreditCardDetailSerializer


class CreditCardEditView(UpdateAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = Card.objects.all()
    serializer_class = CreditCardEditSerializer
    http_method_names = ('patch',)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        card = Card.update(pk=instance.pk, updated_by=request.user, **serializer.validated_data)
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(self.get_serializer(card).data)
        # return Response(status=status.HTTP_200_OK)


class AdaccountCardUpdateView(UpdateAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = AdAccountCreditCard.objects.all()
    serializer_class = AdaccountCreditCardEditSerializer
    http_method_names = ('patch',)

    # FIXME: тут только добавление карты В СРМ.
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(adaccount_card=instance, data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            try:
                if instance.card is not None:
                    credit_card = Card.objects.get(id=instance.card_id)
                else:
                    credit_card = Card.objects.get(number=serializer.validated_data['number'])
                Card.update(
                    pk=credit_card.id, updated_by=request.user, adaccount_card=instance, **serializer.validated_data
                )
            except Card.DoesNotExist:
                credit_card = Card.create(
                    created_by=request.user, adaccount_card=instance, **serializer.validated_data,
                )
            adaccount_card = AdAccountCreditCard.update(pk=instance.pk, updated_by=request.user, card=credit_card)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(status=status.HTTP_200_OK, data={'card_id': adaccount_card.card_id, 'id': adaccount_card.id})


class CreateAdAccountCard(APIView):
    allowed_roles = (
        User.ADMIN,
        User.FINANCIER,
    )

    @swagger_auto_schema(request_body=CreditCardCreateSerializer)
    def post(self, request, *args, **kwargs):
        adaccount = get_object_or_404(AdAccount, id=kwargs['pk'])
        serializer = CreditCardCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = attach_card(
            adaccount=adaccount,
            number=serializer.validated_data['number'],
            cvv=serializer.validated_data['cvv'],
            exp_month=serializer.validated_data['exp_month'],
            exp_year=serializer.validated_data['exp_year'],
        )

        if response and response.status_code == 200:
            adaccount_card = load_adaccount_payment_methods(adaccount)
            if adaccount_card is not None:
                with transaction.atomic():
                    try:
                        if adaccount_card.card is not None:
                            credit_card = Card.objects.get(id=adaccount_card.card_id)
                        else:
                            credit_card = Card.objects.get(number=serializer.validated_data['number'])
                        # print(credit_card)
                        Card.update(
                            pk=credit_card.id,
                            updated_by=request.user,
                            adaccount_card=adaccount_card,
                            **serializer.validated_data,
                        )
                    except Card.DoesNotExist:
                        credit_card = Card.create(
                            created_by=request.user, adaccount_card=adaccount_card, **serializer.validated_data,
                        )
                        # print(credit_card)
                    AdAccountCreditCard.update(pk=adaccount_card.pk, updated_by=request.user, card=credit_card)

            return Response(status=status.HTTP_200_OK)

        elif response:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=response.json().get('error', {}).get('message', 'Unknown FB error'),
            )
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class CreditCardTransactionsViewSet(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = AdAccountTransaction.objects.all()
    serializer_class = TransactionSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = TransactionFilter
    pagination_class = TotalStatsPagination

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        total_stats = self.get_total_stats(queryset)

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response_with_total(serializer.data, total_stats)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # def get_queryset(self) -> QuerySet:
    #     qs = super(CreditCardTransactionsViewSet, self).get_queryset()
    #     if 'card_id' in self.kwargs:
    #         qs = qs.filter(card_id=self.kwargs['card_id'])
    #     return qs

    def get_total_stats(self, queryset: QuerySet):
        queryset = queryset.filter(status='completed')

        refunds = queryset.filter(charge_type='refund')
        spends = queryset.filter(charge_type='payment')

        funds = queryset.filter(charge_type='topup')
        withdraw = queryset.filter(charge_type='withdraw')

        total_refunds = refunds.aggregate(amount=Sum('amount'))
        total_refunds = total_refunds.get('amount') or Decimal('0.00')

        total_spends = spends.aggregate(amount=Sum('amount'))
        total_spends = total_spends.get('amount') or Decimal('0.00')

        total_funds = funds.aggregate(amount=Sum('amount'))
        total_funds = total_funds.get('amount') or Decimal('0.00')

        total_withdraw = withdraw.aggregate(amount=Sum('amount'))
        total_withdraw = total_withdraw.get('amount') or Decimal('0.00')

        fb_spends = total_spends - total_refunds
        funds = total_funds - total_withdraw

        total_stats = {'total_funds': funds, 'total_spends': fb_spends}
        return total_stats

    def get_paginated_response_with_total(self, data, total):
        """
        Return a paginated style `Response` object for the given output data.
        """
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data, total)


class FinAccountListView(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = FinAccount.objects.all()
    serializer_class = FinAccountSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    # filterset_class = TransactionFilter


class FinAccountRetrieveView(DinamicFieldsRetrieveAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = FinAccount.objects.all()
    serializer_class = FinAccountSerializer


class FinAccountCreateView(CreateAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = FinAccount.objects.all()
    serializer_class = FinAccountCreateEditSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        FinAccount.create(created_by=request.user, **serializer.validated_data)
        return Response(status=status.HTTP_201_CREATED)


class FinAccountEditView(UpdateAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = FinAccount.objects.all()
    serializer_class = FinAccountCreateEditSerializer
    http_method_names = ('patch',)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        fin_account = FinAccount.update(pk=instance.pk, updated_by=request.user, **serializer.validated_data)
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(FinAccountSerializer(fin_account).data)
        # return Response(status=status.HTTP_200_OK)
