"""project URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/dev/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views import defaults as default_views

from api.v1 import router as v1_router

urlpatterns = [
    path('grappelli/', include('grappelli.urls')),  # grappelli URLS
    path('wiki/', include('wiki.urls')),
    path(settings.ADMIN_URL, admin.site.urls),
    path('api/v1/', include(v1_router, namespace='v1')),
]

if settings.DEBUG:  # pragma: no cover
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    from django.conf.urls.static import static

    from drf_yasg import openapi
    from drf_yasg.views import get_schema_view
    from rest_framework import permissions

    schema_view = get_schema_view(
        openapi.Info(
            title="CRM REST API docs",
            default_version='v1',
            description="CRM UI API Definition",
            # terms_of_service="https://www.google.com/policies/terms/",
            # contact=openapi.Contact(email="contact@snippets.local"),
            # license=openapi.License(name="BSD License"),
        ),
        public=False,
        permission_classes=(permissions.AllowAny,),
    )

    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    urlpatterns += [
        path("400/", default_views.bad_request, kwargs={"exception": Exception("Bad Request!")}),
        path("403/", default_views.permission_denied, kwargs={"exception": Exception("Permission Denied")}),
        path("404/", default_views.page_not_found, kwargs={"exception": Exception("Page not Found")}),
        path("500/", default_views.server_error),
        path('api/v1/schema/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
        path('api/v1/schema/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    ]
    # urlpatterns += [path('silk/', include('silk.urls', namespace='silk'))]

    # import debug_toolbar
    #
    # urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
