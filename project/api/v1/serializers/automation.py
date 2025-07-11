import os

from django.utils.translation import ugettext_lazy as _

from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers

from api.v1.serializers.accounts import AccountSimpleSerializer
from api.v1.serializers.users import AccountUserSerializer
from core.models.core import (
    AdAccount,
    AdsCreateTask,
    CampaignTemplate,
    FBPage,
    Leadgen,
    Rule,
    UploadedImage,
    UploadedVideo,
)


class MediaSerializer(serializers.Serializer):
    url = serializers.URLField(read_only=True)
    file = serializers.FileField(write_only=True)

    def validate(self, attrs):
        validated_data = super(MediaSerializer, self).validate(attrs)
        validated_data['name'] = os.path.splitext(validated_data['file'].name)[0]
        validated_data['size'] = validated_data['file'].size
        return validated_data

    class Meta:
        fields = (
            'file',
            'url',
            'name',
            'id',
        )


class ImageSerializer(MediaSerializer, serializers.ModelSerializer):
    class Meta(MediaSerializer.Meta):
        model = UploadedImage
        fields = MediaSerializer.Meta.fields + ('thumb_url',)


class VideoSerializer(MediaSerializer, serializers.ModelSerializer):
    class Meta(MediaSerializer.Meta):
        model = UploadedVideo


class TemplateSerializer(serializers.ModelSerializer):
    user = AccountUserSerializer(read_only=True)

    class Meta:
        model = CampaignTemplate
        fields = '__all__'


class AdSerializer(serializers.Serializer):
    CTO_CHOICES = (
        ('OPEN_LINK', 'OPEN_LINK'),
        ('SHOP_NOW', 'SHOP_NOW'),
        ('LEARN_MORE', 'LEARN_MORE'),
        ('SIGN_UP', 'SIGN_UP'),
        ('BUY_NOW', 'BUY_NOW'),
        ('CONTACT_US', 'CONTACT_US'),
        ('ORDER_NOW', 'ORDER_NOW'),
        ('SEE_MORE', 'SEE_MORE'),
        ('LIKE_PAGE', 'LIKE_PAGE'),
        ('NO_BUTTON', 'NO_BUTTON'),
        ('DOWNLOAD', 'DOWNLOAD'),
        ('GET_OFFER', 'GET_OFFER'),
        ('GET_QUOTE', 'GET_QUOTE'),
        ('GET_SHOWTIMES', 'GET_SHOWTIMES'),
        ('REQUEST_TIME', 'REQUEST_TIME'),
        ('SEE_MENU', 'SEE_MENU'),
        ('SUBSCRIBE', 'SUBSCRIBE'),
        ('WATCH_MORE', 'WATCH_MORE'),
        ('LISTEN_NOW', 'LISTEN_NOW'),
        ('APPLY_NOW', 'APPLY_NOW'),
        ('BOOK_TRAVEL', 'BOOK_TRAVEL'),
    )
    name = serializers.CharField(max_length=255)
    message = serializers.CharField(max_length=512, required=False, allow_blank=True)
    description = serializers.CharField(max_length=512, required=False, allow_blank=True)
    headline = serializers.CharField(max_length=512, required=False, allow_blank=True)
    link = serializers.CharField(max_length=4096, required=False, allow_blank=True)
    url_tags = serializers.CharField(max_length=4096, required=False, allow_blank=True)
    caption = serializers.CharField(max_length=512, required=False, allow_blank=True)
    call_to_action = serializers.ChoiceField(choices=CTO_CHOICES)
    leadform = serializers.PrimaryKeyRelatedField(queryset=Leadgen.objects.all(), allow_empty=True, allow_null=True)
    images = serializers.PrimaryKeyRelatedField(queryset=UploadedImage.objects.all(), many=True, allow_empty=False)
    images_data = serializers.SerializerMethodField(read_only=True)
    videos = serializers.PrimaryKeyRelatedField(queryset=UploadedVideo.objects.all(), many=True)
    videos_data = serializers.SerializerMethodField(read_only=True)

    def get_images_data(self, obj):
        return ImageSerializer(obj['images'], many=True).data

    def get_videos_data(self, obj):
        return VideoSerializer(obj['videos'], many=True).data


class AdSetSerializer(serializers.Serializer):
    CUSTOM_EVENT_TYPE_CHOICES = (
        ('INITIATED_CHECKOUT', ' Initiated checkout'),
        ('LEAD', 'Lead'),
    )
    OPTIMIZATION_GOAL_CHOICES = (
        ('OFFSITE_CONVERSIONS', ' OFFSITE_CONVERSIONS'),
        ('PAGE_LIKES', 'PAGE_LIKES'),
        ('LINK_CLICKS', 'LINK_CLICKS'),
        ('LANDING_PAGE_VIEWS', 'LANDING_PAGE_VIEWS'),
        ('IMPRESSIONS', 'IMPRESSIONS'),
        ('REACH', 'REACH'),
        ('LEAD_GENERATION', 'LEAD_GENERATION'),
    )
    name = serializers.CharField(max_length=255)
    ads = AdSerializer(many=True)
    targeting = serializers.JSONField()  # TODO: Сериализатор
    custom_event_type = serializers.ChoiceField(choices=CUSTOM_EVENT_TYPE_CHOICES, required=False)  # Только конверсии
    optimization_goal = serializers.ChoiceField(choices=OPTIMIZATION_GOAL_CHOICES)
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField(required=False, allow_null=True)
    schedule = serializers.JSONField(required=False, allow_null=True)


class CampaignTemplateSerializer(serializers.Serializer):
    OBJECTIVE_CHOICES = (
        ('PAGE_LIKES', 'Page Likes'),
        ('CONVERSIONS', 'Conversions'),
        ('LINK_CLICKS', 'Traffic'),
        ('LEAD_GENERATION', 'Lead Generation'),
    )

    name = serializers.CharField(max_length=255)
    objective = serializers.ChoiceField(choices=OBJECTIVE_CHOICES)
    adsets = AdSetSerializer(many=True)


class AdAccoundDataSerializer(serializers.Serializer):
    adaccount = serializers.PrimaryKeyRelatedField(queryset=AdAccount.objects.all())
    page = serializers.PrimaryKeyRelatedField(queryset=FBPage.objects.all())
    rules = serializers.PrimaryKeyRelatedField(
        queryset=Rule.objects.all(), allow_null=False, required=False, many=True
    )
    pixel = serializers.IntegerField(required=False, allow_null=True)
    daily_budget = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    lifetime_budget = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    campaign = CampaignTemplateSerializer()


class AdsCreateTaskCreateSerializer(serializers.Serializer):
    adaccounts = AdAccoundDataSerializer(
        many=True, required=True, allow_null=False, allow_empty=False, write_only=True
    )
    template = serializers.PrimaryKeyRelatedField(queryset=CampaignTemplate.objects.all())


class AdsCreateLogListSerializer(FlexFieldsModelSerializer):
    # TODO: сделать нормально
    user = AccountUserSerializer(read_only=True)
    account = AccountSimpleSerializer()
    adaccount = serializers.SerializerMethodField()
    template = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    campaign = serializers.SerializerMethodField()

    def get_campaign(self, obj):
        return obj.campaign_data

    def get_adaccount(self, obj):
        data = obj.adaccount_data
        data.update(
            {
                'name': obj.adaccount.name,
                'pixels': obj.adaccount.pixels,
                'business_id': obj.adaccount.business_id if obj.adaccount.business else None,
                'business_name': obj.adaccount.business.name if obj.adaccount.business else None,
            }
        )
        return data

    def get_template(self, obj):
        if obj.template:
            return {
                'id': obj.template_id,
                'name': obj.template.name,
            }
        else:
            return None

    def get_status(self, obj):
        return {
            'status': obj.status,
            'title': obj.get_status_display(),
            'status_comment': obj.status_comment,
        }

    class Meta:
        model = AdsCreateTask
        fields = ('id', 'user', 'account', 'adaccount', 'template', 'created_at', 'status', 'campaign')


class FilterSerializer(serializers.Serializer):
    field = serializers.CharField(max_length=32)
    operator = serializers.CharField(max_length=32)
    value = serializers.CharField(max_length=256)  # TODO: для разных операторов разные типы поля


class EvaluationSpecSerializer(serializers.Serializer):
    EVALUATION_TYPE_CHOICES = (
        ('SCHEDULE', 'SCHEDULE'),
        ('TRIGGER', 'TRIGGER'),
    )
    evaluation_type = serializers.ChoiceField(choices=EVALUATION_TYPE_CHOICES)
    filters = FilterSerializer(many=True)


class ScheduleSpecSerializer(serializers.Serializer):
    SCHEDULE_TYPE_CHOICES = (
        ('DAILY', _('DAILY')),
        ('HOURLY', _('HOURLY')),
        ('SEMI_HOURLY', _('SEMI_HOURLY')),
        ('CUSTOM', _('CUSTOM')),
    )

    schedule_type = serializers.ChoiceField(choices=SCHEDULE_TYPE_CHOICES)
    schedule = serializers.ListField(allow_empty=True, allow_null=True, required=False)


class ExcecutionSpecSerializer(serializers.Serializer):
    EXCECUTION_TYPE_CHOICES = (('PAUSE', _('PAUSE')), ('UNPAUSE', _('UNPAUSE')))

    execution_type = serializers.ChoiceField(choices=EXCECUTION_TYPE_CHOICES)


class QuestionSerializer(serializers.Serializer):
    key = serializers.CharField()
    type = serializers.CharField()  # TODO: choices


class LeadgenDataSerializer(serializers.Serializer):
    locale = serializers.CharField()  # TODO: choices
    context_card = serializers.JSONField()
    cover_photo = serializers.IntegerField(required=False)
    cover_photo_data = serializers.SerializerMethodField()
    privacy_policy = serializers.JSONField()
    thank_you_page = serializers.JSONField()
    question_page_custom_headline = serializers.CharField()
    block_display_for_non_targeted_viewer = serializers.BooleanField(default=True, required=False)
    questions = QuestionSerializer(many=True)

    def get_cover_photo_data(self, obj):
        if 'cover_photo' in obj:
            cover_photo = UploadedImage.objects.get(id=obj['cover_photo'])
            return ImageSerializer(cover_photo).data
        return {}


class LeadgenSerializer(FlexFieldsModelSerializer):
    user = AccountUserSerializer(read_only=True)
    data = LeadgenDataSerializer()

    class Meta:
        model = Leadgen
        fields = '__all__'


class RuleSerializer(FlexFieldsModelSerializer):
    user = AccountUserSerializer(read_only=True)
    evaluation_spec = EvaluationSpecSerializer()
    schedule_spec = ScheduleSpecSerializer()
    execution_spec = ExcecutionSpecSerializer()

    class Meta:
        model = Rule
        fields = '__all__'
