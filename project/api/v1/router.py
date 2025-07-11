from typing import List

from django.conf import settings
from django.urls import path, re_path

from knox.views import LogoutView
from rest_framework import routers

from api.v1.views.accounts import (
    AccountCreateView,
    AccountDetailView,
    AccountDetailViewFB,
    AccountEditView,
    AccountListView,
    AccountLogListView,
    AccountPaymentData,
    AccountPaymentDone,
    AccountPaymentsListView,
    AccountStatusView,
    BusinessCreateView,
    FanPageCreateView,
    PaymentHystoryView,
)
from api.v1.views.adaccounts import (
    AdAccountCreateRule,
    AdAccountEditView,
    AdAccountsListView,
    AdAccountStartStopCampaings,
    AdAccountsView,
)
from api.v1.views.automation import (
    AdsCreateLogListView,
    AdsCreateLogRetrieveView,
    AdsCreateView,
    AdsRecreateView,
    ImagesListView,
    ImageUploadView,
    LeadgenCopyView,
    LeadgenViewSet,
    RulesViewSet,
    TemplateCopyView,
    TemplatesViewSet,
    VideoListView,
    VideoUploadView,
)
from api.v1.views.businesses import (
    BusinessManagerActionsLog,
    BusinessManagerLogListView,
    BusinessShareListView,
    BusinessShareUrlCreateView,
)
from api.v1.views.contacts import ContactAnswersCreateView, ContactCreateView, ContactPostbackView, ContactViewSet
from api.v1.views.core import (
    CampaignsViewSet,
    CountriesViewSet,
    CreateMLAProfiles,
    CSVUploadView,
    FBPageViewSet,
    KPIViewSet,
    PageCategoriesViewSet,
    ProxiesStatus,
    ShortifyDomainsViewSet,
    StopAllAds,
    TagViewSet,
    TelegramWebhookView,
    CreateXCards,
)
from api.v1.views.finances import (
    AdaccountCardListView,
    AdaccountCardUpdateView,
    CreateAdAccountCard,
    CreditCardEditView,
    CreditCardRetrieveView,
    CreditCardTransactionsViewSet,
    FinAccountCreateView,
    FinAccountListView,
    FinAccountRetrieveView,
)
from api.v1.views.leads import (
    LeadgenBroadcastCreateView,
    LeadgenBroadcastEditView,
    LeadgenBroadcastListView,
    LeadgenBroadcastRecreateView,
    LeadgenClickPostbackView,
    LeadgenLanderPostbackView,
    LeadgenLeadPostbackView,
    LeadgenLeadViewSet,
)
from api.v1.views.manychat import (
    ManychatDateMessage,
    ManychatMatchingMessage,
    ManychatPhotoMessage,
    ManychatPostbackTagView,
    ManychatSaveTokenMessage,
)
from api.v1.views.notifications import NotificationsListReadView, NotificationsListView
from api.v1.views.stats import (
    AccountsStatView,
    AccountStatusStatsView,
    AdAccountsStatView,
    CampaignStatView,
    DateStatView,
    FlowsStatView,
    GeoGlobalStats,
    GeoUserStats,
    LeadgenLeadStats,
    LifetimeSpendView,
    StatusDurationView,
    TotalBannedView,
    UserBaseStats,
    UsersStatView,
)
from api.v1.views.user_requests import (
    RequestCreateView,
    RequestsAccountListView,
    RequestsFixListView,
    RequestsMoneyListView,
    RequestsSetupListView,
    RequestUpdateView,
)
from api.v1.views.users import (
    FieldsSettingsView,
    LoginAPIView,
    TeamViewSet,
    TelegramConnectView,
    UserActionsLogListView,
    UserChangePasswordView,
    UserCreateView,
    UserDetailView,
    UserEditView,
    UserListView,
    UserNotificationSettings,
    UserProfileViewSet,
    UserTotalStatsView,
)

router = routers.DefaultRouter()

urlpatterns: List[str] = []

# Auth endpoints
urlpatterns += [
    # returns token + user_data
    path('auth/token/<str:provider>/', TelegramConnectView.as_view()),
    path('auth/login/', LoginAPIView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('webhook/bpQ6K3zGnuh66TPU/', TelegramWebhookView.as_view(), name='webhook'),
]

# requests endoints
urlpatterns += [
    path('requests/money/', RequestsMoneyListView.as_view()),
    path('requests/accounts/', RequestsAccountListView.as_view()),
    path('requests/fix/', RequestsFixListView.as_view()),
    path('requests/setup/', RequestsSetupListView.as_view()),
    # path('requests/', RequestsListView.as_view()),
    path('requests/create/', RequestCreateView.as_view()),
    path('requests/<int:pk>/update/', RequestUpdateView.as_view()),
]

urlpatterns += [
    path('tools/mla/create/', CreateMLAProfiles.as_view()),
    path('tools/ads/stop/', StopAllAds.as_view()),
    path('tools/csv/import/<str:type>/', CSVUploadView.as_view()),
    path('tools/proxies/', ProxiesStatus.as_view()),
    path('tools/cards/', CreateXCards.as_view()),
]

# cards endoints
urlpatterns += [
    path('cards/<int:pk>/', CreditCardRetrieveView.as_view()),
    path('cards/<int:pk>/update/', CreditCardEditView.as_view()),
    path('adaccount_cards/', AdaccountCardListView.as_view()),
    path('adaccount_cards/<int:pk>/update/', AdaccountCardUpdateView.as_view()),
    path('transactions/', CreditCardTransactionsViewSet.as_view()),
]

# Users
urlpatterns += [
    path('users/', UserListView.as_view()),
    path('users/create/', UserCreateView.as_view()),
    path('users/<int:pk>/', UserDetailView.as_view()),
    path('users/<int:pk>/update/', UserEditView.as_view()),
    path('users/<int:pk>/password/', UserChangePasswordView.as_view()),
    path('users/<int:pk>/notifications/settings/', UserNotificationSettings.as_view()),
    path('users/<int:pk>/log/', UserActionsLogListView.as_view()),
    path('users/<int:pk>/stats/total/', UserTotalStatsView.as_view()),  # TODO: перенести в стату основную
]

# misc
urlpatterns += [
    path('profile/', UserProfileViewSet.as_view(actions={'get': 'retrieve'})),
    path('notifications/', NotificationsListView.as_view()),
    path('notifications/read/', NotificationsListReadView.as_view()),
    path('fields/<str:slug>/<str:action>/', FieldsSettingsView.as_view()),
]

# accounts endpoints
urlpatterns += [
    path('accounts/', AccountListView.as_view()),
    path('accounts/create/', AccountCreateView.as_view()),
    # path('accounts/queue/', AccountsQueueView.as_view()),
    path('accounts/payment/', AccountPaymentData.as_view()),
    path('accounts/payment/history/', PaymentHystoryView.as_view()),
    path('accounts/payment/done/', AccountPaymentDone.as_view()),
    path('accounts/fb/<int:fb_id>/', AccountDetailViewFB.as_view()),
    path('accounts/<int:pk>/', AccountDetailView.as_view()),
    path('accounts/<int:pk>/update/', AccountEditView.as_view()),
    path('accounts/<int:pk>/status/', AccountStatusView.as_view()),
    path('accounts/<int:pk>/businesses/create/', BusinessCreateView.as_view()),
    path('accounts/<int:pk>/page/create/', FanPageCreateView.as_view()),
    path('accounts/<int:pk>/adaccounts/', AdAccountsListView.as_view()),
    path('accounts/<int:account_id>/adaccounts/<int:pk>/update/', AdAccountEditView.as_view()),
    path('accounts/<int:account_id>/log/', AccountLogListView.as_view()),
    path('accounts/<int:account_id>/payments/', AccountPaymentsListView.as_view()),
]
# Business endpoints
urlpatterns += [
    path('businesses/<int:business_id>/share/', BusinessShareListView.as_view()),
    path('businesses/<int:business_id>/share/create/', BusinessShareUrlCreateView.as_view()),
    path('businesses/<int:business_id>/actions/', BusinessManagerActionsLog.as_view()),
    path('businesses/<int:business_id>/log/', BusinessManagerLogListView.as_view()),
]

# FIN endpoints
urlpatterns += [
    path('finaccounts/', FinAccountListView.as_view()),
    path('finaccounts/create/', FinAccountCreateView.as_view()),
    path('finaccounts/<int:pk>/', FinAccountRetrieveView.as_view()),
    path('finaccounts/<int:pk>/update/', FinAccountRetrieveView.as_view()),
]

# stats endpoints
urlpatterns += [
    # path('stats/user/', UserStatListView.as_view()),  # TODO: del
    # path('stats/team/', TeamStatListView.as_view()),  # TODO: del
    path('stats/geo/', GeoUserStats.as_view()),
    path('stats/geo/global/', GeoGlobalStats.as_view()),
    path('stats/base/', UserBaseStats.as_view()),
    path('stats/statuses/durations/', StatusDurationView.as_view()),
    path('stats/date/', DateStatView.as_view()),
    path('stats/campaigns/', CampaignStatView.as_view()),
    path('stats/accounts/', AccountsStatView.as_view()),
    path('stats/adaccounts/', AdAccountsStatView.as_view()),
    path('stats/users/', UsersStatView.as_view()),
    path('stats/flows/', FlowsStatView.as_view()),
    path('stats/statuses/total/', AccountStatusStatsView.as_view()),
    path('stats/spends/', LifetimeSpendView.as_view()),
    path('stats/bans/', TotalBannedView.as_view()),
]

# Automation
urlpatterns += [
    path('rules/', RulesViewSet.as_view(actions={'get': 'list'})),
    path('rules/create/', RulesViewSet.as_view(actions={'post': 'create'})),
    path('rules/<int:pk>/', RulesViewSet.as_view(actions={'get': 'retrieve', 'delete': 'destroy'})),
    path('rules/<int:pk>/update/', RulesViewSet.as_view(actions={'patch': 'update'})),
    path('templates/', TemplatesViewSet.as_view(actions={'get': 'list'})),
    path('templates/<int:pk>/', TemplatesViewSet.as_view(actions={'get': 'retrieve', 'delete': 'destroy'})),
    path('templates/<int:pk>/update/', TemplatesViewSet.as_view(actions={'patch': 'update'})),
    path('templates/<int:pk>/copy/', TemplateCopyView.as_view()),
    path('templates/create/', TemplatesViewSet.as_view(actions={'post': 'create'})),
    path('images/upload/', ImageUploadView.as_view()),
    path('videos/upload/', VideoUploadView.as_view()),
    path('images/', ImagesListView.as_view(actions={'get': 'list'})),
    path('images/<int:pk>/', ImagesListView.as_view(actions={'get': 'retrieve', 'delete': 'destroy'})),
    path('videos/', VideoListView.as_view(actions={'get': 'list'})),
    path('videos/<int:pk>/', VideoListView.as_view(actions={'get': 'retrieve', 'delete': 'destroy'})),
    path('adaccounts/', AdAccountsView.as_view()),  # FIXME
    path('adaccounts/<int:pk>/card/create/', CreateAdAccountCard.as_view()),
    path('adaccounts/<int:pk>/rules/create/', AdAccountCreateRule.as_view()),
    re_path(r'^adaccounts/(?P<action>start|stop)/', AdAccountStartStopCampaings.as_view()),  # FIXME
    path('ads/create/', AdsCreateView.as_view()),
    path('ads/<int:pk>/retry/', AdsRecreateView.as_view()),  # FIXME
    path('ads/create/log/', AdsCreateLogListView.as_view()),
    path('ads/create/log/<int:pk>/', AdsCreateLogRetrieveView.as_view()),
]

# Leadgens
urlpatterns += [
    path('leadgen/', LeadgenViewSet.as_view(actions={'get': 'list'})),
    path('leadgen/create/', LeadgenViewSet.as_view(actions={'post': 'create'})),
    path('leadgen/<int:pk>/', LeadgenViewSet.as_view(actions={'get': 'retrieve', 'delete': 'destroy'})),
    path('leadgen/<int:pk>/update/', LeadgenViewSet.as_view(actions={'patch': 'update'})),
    path('leadgen/<int:pk>/copy/', LeadgenCopyView.as_view()),
]

# KPIs
urlpatterns += [
    path('kpi/', KPIViewSet.as_view(actions={'get': 'list'})),
    path('kpi/create/', KPIViewSet.as_view(actions={'post': 'create'})),
    path('kpi/<int:pk>/', KPIViewSet.as_view(actions={'get': 'retrieve', 'delete': 'destroy'})),
    path('kpi/<int:pk>/update/', KPIViewSet.as_view(actions={'patch': 'update'})),
]

# Contacts
urlpatterns += [
    path('contacts/', ContactViewSet.as_view()),
    path('contacts/create/', ContactCreateView.as_view()),
    path('contacts/create/answers/', ContactAnswersCreateView.as_view()),
    path('contacts/postback/', ContactPostbackView.as_view()),
    path('leads/', LeadgenLeadViewSet.as_view()),
    path('leads/stats/', LeadgenLeadStats.as_view()),
    # path('leads/export/', LeadgenLeadExportView.as_view()),
    path('leads/broadcasts/', LeadgenBroadcastListView.as_view()),
    path('leads/broadcasts/create/', LeadgenBroadcastCreateView.as_view()),
    path('leads/broadcasts/<int:pk>/retry/', LeadgenBroadcastRecreateView.as_view()),
    path('leads/broadcasts/<int:pk>/update/', LeadgenBroadcastEditView.as_view()),
    path('leads/postback/', LeadgenLeadPostbackView.as_view()),
    path('leads/postback/click/', LeadgenClickPostbackView.as_view()),
    path('lander/', LeadgenLanderPostbackView.as_view()),
]


router.register(r'teams', TeamViewSet)
router.register(r'fbpages', FBPageViewSet)
router.register(r'tags', TagViewSet)
router.register(r'countries', CountriesViewSet)
router.register(r'categories', PageCategoriesViewSet)
router.register(r'domains', ShortifyDomainsViewSet)
router.register(r'campaigns', CampaignsViewSet)

if not settings.DEBUG:
    # Manychat endpoints
    urlpatterns += [
        path('manychat/date/', ManychatDateMessage.as_view()),
        path('manychat/photo/', ManychatPhotoMessage.as_view()),
        path('manychat/matching/', ManychatMatchingMessage.as_view()),
        path('manychat/postback/', ManychatPostbackTagView.as_view()),
        path('manychat/save_token/', ManychatSaveTokenMessage.as_view()),
    ]


app_name = 'api'

urlpatterns += router.urls
