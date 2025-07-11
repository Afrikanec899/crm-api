from django.urls import reverse


def test_webhooks():
    assert reverse('v1:api_token_auth') == '/api/v1/auth/login/'
