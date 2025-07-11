import os

import pytest

from core.models import User

from .factories import UserFactory


def load_fixture(name, format='json'):
    with open(os.path.dirname(__file__) + '/fixtures/%s.%s' % (name, format), 'r') as f:
        return f.read()


@pytest.fixture
def user() -> User:
    return UserFactory()
