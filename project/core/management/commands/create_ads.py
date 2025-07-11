from django.core.management.base import BaseCommand

# from core.tasks import create_ads
from core.tasks import CreateAds


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        adaccount = {'id': 16, 'page': 114533836907084, 'rule': None, 'pixel': '4029351457105031', 'daily_budget': 1}

        data = {
            'campaign': {
                'name': 'Likes',
                'adsets': [
                    {
                        'ads': [
                            {
                                'name': 'ad 1',
                                'message': 'sdfsdfsdf',
                                'description': '',
                                'headline': '',
                                'link': '',
                                'caption': '',
                                'call_to_action': {'type': 'LIKE_PAGE'},
                                'images': [16],
                                'videos': [1],
                            }
                        ],
                        'name': 'ad set 1',
                        'targeting': {
                            'age_max': '65',
                            'age_min': '18',
                            'genders': [0],
                            'geo_locations': {'countries': ['UA']},
                            'device_platforms': ['mobile', 'desktop'],
                            'facebook_positions': ['feed'],
                            'publisher_platforms': ['facebook'],
                        },
                        'start_time': '2020-05-07T17:14:00.325+03:00',
                    }
                ],
                'objective': 'PAGE_LIKES',
            }
        }
        create_ads = CreateAds()
        create_ads.run(adaccount, data)
