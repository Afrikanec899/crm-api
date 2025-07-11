import json
from typing import Any
from typing import Sequence as SequenceType

from django.contrib.auth import get_user_model

from factory import DictFactory, DjangoModelFactory, LazyAttribute, post_generation
from faker import Faker

fake = Faker()


class JSONFactory(DictFactory):
    """
    Use with factory.Dict to make JSON strings.
    """

    @classmethod
    def _generate(cls, create, attrs):
        obj = super()._generate(create, attrs)
        return json.dumps(obj)


class UserFactory(DjangoModelFactory):
    username = LazyAttribute(lambda _: fake.user_name())
    email = LazyAttribute(lambda _: fake.email())
    first_name = LazyAttribute(lambda _: fake.first_name())
    last_name = LazyAttribute(lambda _: fake.last_name())

    @post_generation
    def password(self, create: bool, extracted: SequenceType[Any], **kwargs) -> None:
        password = fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True)
        self.set_password(password)

    class Meta:
        model = get_user_model()
        django_get_or_create = ['username']
