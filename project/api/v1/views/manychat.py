import datetime
import logging
import os
import time
from io import BytesIO

from django.conf import settings
from django.utils import timezone

import requests
from PIL import Image, ImageDraw, ImageFont
from pilkit.processors import SmartResize
from redis import Redis
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from slugify import slugify

from api.v1.serializers.manychat import (
    ManyChatDateMessageSerializer,
    ManyChatImageMessageSerializer,
    ManyChatMatchingSerializer,
    ManychatPostbackSerializer,
    SaveTokenDataSerializer,
)
from core.tasks.core import save_subscribers_data
from core.utils import func_attempts

redis = Redis(host='redis', db=0, decode_responses=True)
logger = logging.getLogger('django.request')


class ManychatDateMessage(APIView):
    permission_classes = ()

    def get(self, request, **kwargs):
        serializer = ManyChatDateMessageSerializer(data=request.headers)
        serializer.is_valid(raise_exception=True)

        api_url = f'https://api.manychat.com/fb/subscriber/getInfo?subscriber_id={serializer.validated_data["userid"]}'
        headers = {'Authorization': f'Bearer {serializer.validated_data["key"]}'}
        try:
            user_data = func_attempts(requests.get, api_url, headers=headers, attempts=3).json().get('data')
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if not user_data:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        timezone_offset = user_data['timezone'].replace('UTC', '')
        timezone_offset = timezone_offset.replace('+', '').replace('±', '')
        timezone_offset = int(timezone_offset)
        if timezone_offset > 0:
            user_date = timezone.now() + datetime.timedelta(hours=timezone_offset)
        else:
            user_date = timezone.now() - datetime.timedelta(hours=timezone_offset)

        giveaway_date = user_date + datetime.timedelta(hours=serializer.validated_data['timeadd'])
        giveaway_date += datetime.timedelta(hours=1)
        giveaway_date = giveaway_date.replace(minute=0, second=0, microsecond=0, tzinfo=None)

        time = giveaway_date.strftime('%H:%M')
        date = giveaway_date.strftime('%d.%m.%Y')
        message_text = serializer.validated_data['text'].format(time=time, date=date)

        response = {"version": "v2", "content": {"messages": [{"type": "text", "text": message_text}]}}

        return Response(data=response, status=status.HTTP_200_OK)


class ManychatMatchingMessage(APIView):
    permission_classes = ()

    def get(self, request, **kwargs):
        st = time.time()
        image = Image.new('RGBA', (1024, 1024), (255, 255, 255, 0))
        matching = Image.open(os.path.join(settings.STATIC_ROOT, 'matching.png')).convert('RGBA')

        # data = {
        #     'key': '218181734930729:fa9d37a8d4f9b2844d3485403d216b48',
        #     'userid': '2014419038626926',
        # }
        #
        # serializer = ManyChatMatchingSerializer(data=data)
        serializer = ManyChatMatchingSerializer(data=request.headers)
        serializer.is_valid(raise_exception=True)

        expired = 60 * 60 * 24 * 31
        redis.setex(
            f'manychat_api_key_{serializer.validated_data["userid"]}_{serializer.validated_data["pageid"]}',
            expired,
            serializer.validated_data["key"],
        )

        api_url = f'https://api.manychat.com/fb/subscriber/getInfo?subscriber_id={serializer.validated_data["userid"]}'
        headers = {'Authorization': f'Bearer {serializer.validated_data["key"]}'}
        try:
            user_data = requests.get(api_url, headers=headers, timeout=3).json().get('data')
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if not user_data:
            logger.error('User data is empty', extra={'api_url': api_url, 'headers': headers})
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if not user_data['profile_pic']:
            logger.error('profile_pic data is empty', extra={'user_data': user_data})

        try:
            profile_pic = requests.get(user_data['profile_pic'], timeout=3)
            profile_image = Image.open(BytesIO(profile_pic.content))
            processor = SmartResize(320, 320)
            profile_image = processor.process(profile_image)
        except Exception as e:
            logger.error(e, exc_info=True)
            time.sleep(3)
            try:
                profile_pic = requests.get(user_data['profile_pic'], timeout=3)
                profile_image = Image.open(BytesIO(profile_pic.content))
                processor = SmartResize(320, 320)
                profile_image = processor.process(profile_image)
            except Exception as e:
                logger.error(e, exc_info=True)
                profile_image = Image.open(os.path.join(settings.STATIC_ROOT, 'avatar.png')).convert('RGBA')

        image.paste(profile_image, (352, 352), profile_image)
        image.paste(matching, (0, 0), mask=matching)

        file_name = f'{serializer.validated_data["userid"]}.jpg'
        dir_name = f'matching/{timezone.now().date()}'

        dir_path = os.path.join(settings.MEDIA_ROOT, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        image = image.convert('RGB')
        image.save(os.path.join(dir_path, file_name), 'JPEG', subsampling=0, quality=80)

        image_url = f'https://api.holyaff.com/media/{dir_name}/{file_name}'
        response = {"version": "v2", "content": {"messages": [{"type": "image", "url": image_url}]}}
        proessing_time = time.time() - st

        logging.getLogger('crm.info').info('Procesing time ', extra={'proessing_time': proessing_time})
        return Response(data=response, status=status.HTTP_200_OK)


class ManychatPostbackTagView(APIView):
    permission_classes = ()

    def get(self, request, **kwargs):
        serializer = ManychatPostbackSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data['var1']
        page_id = serializer.validated_data['var2']

        key = redis.get(f'manychat_api_key_{user_id}_{page_id}')

        if not key:
            logger.error(f'Api key not found for user {user_id}, page {page_id}')
            return Response(status=status.HTTP_400_BAD_REQUEST)

        api_url = f'https://api.manychat.com/fb/subscriber/addTagByName'
        headers = {'Authorization': f'Bearer {key}'}  # type:ignore
        data = {'subscriber_id': user_id, 'tag_name': 'converted'}

        try:
            func_attempts(requests.post, api_url, headers=headers, data=data, attempts=3)
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_200_OK)


class ManychatPhotoMessage(APIView):
    permission_classes = ()

    def get_min_font_size(self, strings, max_width, max_font_size, min_font_size=16):
        font_size = max_font_size
        for string in strings:
            while True:
                name_font = ImageFont.truetype(os.path.join(settings.STATIC_ROOT, 'Akrobat-Bold.ttf'), font_size)
                name_text_w, name_text_h = name_font.getsize(string)
                if name_text_w <= max_width or font_size <= min_font_size:
                    break
                font_size -= 2

        return font_size

    def get(self, request, **kwargs):
        image = Image.new('RGBA', (960, 817), (255, 255, 255, 0))
        winners = Image.open(os.path.join(settings.STATIC_ROOT, 'winners.png')).convert('RGBA')

        # data = {
        #     'key': '218181734930729:fa9d37a8d4f9b2844d3485403d216b48',
        #     'userid': '2014419038626926',
        #     'text': 'Samsung Galaxy S9 Winners',
        #     'name1': 'Toussaint Simon',
        #     'name2': 'Rosemarie Cousteau',
        # }
        #
        # serializer = ManyChatImageMessageSerializer(data=data)
        serializer = ManyChatImageMessageSerializer(data=request.headers)
        serializer.is_valid(raise_exception=True)

        api_url = f'https://api.manychat.com/fb/subscriber/getInfo?subscriber_id={serializer.validated_data["userid"]}'
        headers = {'Authorization': f'Bearer {serializer.validated_data["key"]}'}
        try:
            user_data = func_attempts(requests.get, api_url, headers=headers, attempts=3).json().get('data')
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if not user_data:
            logger.error('User data is empty', extra={'api_url': api_url})
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if not user_data['profile_pic']:
            logger.error('profile_pic data is empty', extra=user_data)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        profile_image = Image.open(requests.get(user_data['profile_pic'], stream=True).raw)
        processor = SmartResize(285, 325)
        profile_image = processor.process(profile_image)
        image.paste(profile_image, (340, 365), profile_image)
        image.paste(winners, (0, 0), mask=winners)

        draw = ImageDraw.Draw(image)
        # Header
        header_block_w, header_block_h = (582, 58)
        header_font_size = self.get_min_font_size(
            [serializer.validated_data["text"]], max_width=header_block_w, max_font_size=40
        )
        header_font = ImageFont.truetype(os.path.join(settings.STATIC_ROOT, 'Akrobat-Bold.ttf'), header_font_size)
        header_text_w, header_text_h = header_font.getsize(serializer.validated_data["text"])

        w_offset = (header_block_w - header_text_w) / 2
        h_offset = (header_block_h - header_text_h) / 2
        draw.text(
            (184 + w_offset, 54 + h_offset), serializer.validated_data["text"], (255, 255, 255), font=header_font
        )

        # Names
        name_block_w, name_block_h = (232, 75)
        # Name1
        names = [serializer.validated_data["name1"], serializer.validated_data["name2"], user_data['name']]
        font_size = self.get_min_font_size(names, max_width=name_block_w, max_font_size=30)
        name_font = ImageFont.truetype(os.path.join(settings.STATIC_ROOT, 'Akrobat-Bold.ttf'), font_size)

        name_text_w, name_text_h = name_font.getsize(serializer.validated_data["name1"])
        w_offset = (name_block_w - name_text_w) / 2
        h_offset = (name_block_h - name_text_h) / 2
        draw.text((95 + w_offset, 518 + h_offset), serializer.validated_data["name1"], (196, 121, 2), font=name_font)

        # Name2
        name_text_w, name_text_h = name_font.getsize(serializer.validated_data["name2"])
        w_offset = (name_block_w - name_text_w) / 2
        h_offset = (name_block_h - name_text_h) / 2
        draw.text((635 + w_offset, 518 + h_offset), serializer.validated_data["name2"], (196, 121, 2), font=name_font)

        # Name winner
        name_text_w, name_text_h = name_font.getsize(user_data['name'])
        w_offset = (name_block_w - name_text_w) / 2
        h_offset = (name_block_h - name_text_h) / 2
        draw.text((366 + w_offset, 686 + h_offset), user_data['name'], (196, 121, 2), font=name_font)

        file_name = f'{slugify(serializer.validated_data["text"])}-{serializer.validated_data["userid"]}.jpg'
        dir_name = f'winners/{timezone.now().date()}'

        dir_path = os.path.join(settings.MEDIA_ROOT, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        image = image.convert('RGB')
        image.save(os.path.join(dir_path, file_name), 'JPEG', subsampling=0, quality=80)

        image_url = f'https://api.holyaff.com/media/{dir_name}/{file_name}'
        response = {"version": "v2", "content": {"messages": [{"type": "image", "url": image_url}]}}

        return Response(data=response, status=status.HTTP_200_OK)


class ManychatSaveTokenMessage(APIView):
    permission_classes = ()

    def get(self, request, **kwargs):
        serializer = SaveTokenDataSerializer(data=request.headers)
        serializer.is_valid(raise_exception=True)

        expired = 60 * 60 * 24 * 31
        redis.setex(
            f'manychat_api_key_{serializer.validated_data["userid"]}_{serializer.validated_data["pageid"]}',
            expired,
            serializer.validated_data["key"],
        )
        if serializer.validated_data.get('email'):
            save_subscribers_data.delay(
                user_id=serializer.validated_data["userid"],
                page_id=serializer.validated_data["pageid"],
                email=serializer.validated_data.get('email'),
                phone=serializer.validated_data.get('phone'),
            )

        response = {"version": "v2", "content": {"actions": []}}
        return Response(data=response, status=status.HTTP_200_OK)
