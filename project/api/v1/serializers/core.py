from rest_framework import serializers

from core.models.core import Action, Country, FBPage, Flow, PageCategory, ShortifyDomain, UserKPI


class ActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Action
        fields = '__all__'


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('name', 'code', 'id')


class ShortifyDomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortifyDomain
        fields = ('domain', 'id')


class PageCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PageCategory
        fields = ('name', 'fb_id', 'id')


class FlowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flow
        fields = ('flow_name', 'id')


class CountSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=1, max_value=50)


class KPISerializer(serializers.ModelSerializer):
    #  Так как это поле только для отдачи на фронт, то CharField для сохранения родного типа данных в ответе
    current_value = serializers.CharField(read_only=True, max_length=32)

    class Meta:
        model = UserKPI
        fields = '__all__'


# Fb page TODO: Вынести куда-то
class FBPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = FBPage
        fields = ('id', 'name', 'page_id')
