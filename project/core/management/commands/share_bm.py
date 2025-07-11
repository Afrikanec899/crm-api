import random
import time

from django.core.management.base import BaseCommand

from facebook_business import FacebookAdsApi
from facebook_business.adobjects.business import Business
from facebook_business.adobjects.user import User as FBUser
from faker import Faker


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        proxy = {}
        proxy['https'] = 'https://proxy:yPslpDgasGo465htsl@proxy.holyaff.com:3128'

        tokens = [
            'EAABsbCS1iHgBAJJkOygNsaOgQ24BZC8U5keN0hBVCn8sYNJZCAe85gdYp3AklkzZCyzWxDPjm4xFzP58BBdST7mSjt8Y4GOzYH31q3ZBDnlTWLZAhhbVIoB2mwm1r32XboaqYWeDD2smxnovz2Q0FNP8psu3jauceLplgodXVnAZDZD',
            'EAABsbCS1iHgBAJJkOygNsaOgQ24BZC8U5keN0hBVCn8sYNJZCAe85gdYp3AklkzZCyzWxDPjm4xFzP58BBdST7mSjt8Y4GOzYH31q3ZBDnlTWLZAhhbVIoB2mwm1r32XboaqYWeDD2smxnovz2Q0FNP8psu3jauceLplgodXVnAZDZD',
            'EAABsbCS1iHgBAPk3ZA8I9vkL4CZBKMmUHWZAlhxpC8efnAYM6Ui6VWqn7f66N78DJABCIaY01doL7JblDqBkmFp3JTXki4QCM9hwo3c7wpVWaEZCVrltuWbpgooZCMX4kpOlXZBBi44BqOo5hnWgDgaEikWhVNl4jKjp7hLS659QZDZD',
            'EAABsbCS1iHgBAPk3ZA8I9vkL4CZBKMmUHWZAlhxpC8efnAYM6Ui6VWqn7f66N78DJABCIaY01doL7JblDqBkmFp3JTXki4QCM9hwo3c7wpVWaEZCVrltuWbpgooZCMX4kpOlXZBBi44BqOo5hnWgDgaEikWhVNl4jKjp7hLS659QZDZD',
            'EAABsbCS1iHgBAETY8vSDmQpj71HbGzoTKCTNAB05Twm5s59GEhUE8quqtjcXTUEAzP2u3YN7fEaZCZAAiX2daYy7oyUjk0MJ46O9FwpHWc5sxXZA3pjGgAmm35ZBDjRvUwF4Lm1d3qickgbnKe3ovdCdchZAH4OXQPmFOxwrAbgZDZD',
            'EAABsbCS1iHgBAETY8vSDmQpj71HbGzoTKCTNAB05Twm5s59GEhUE8quqtjcXTUEAzP2u3YN7fEaZCZAAiX2daYy7oyUjk0MJ46O9FwpHWc5sxXZA3pjGgAmm35ZBDjRvUwF4Lm1d3qickgbnKe3ovdCdchZAH4OXQPmFOxwrAbgZDZD',
            'EAABsbCS1iHgBAK2WHx73vqcH3gZCwAegfbzynqkyXagktVLuZAHftL8CpGZB7Fi0NyasujFDEWxtUpMcWwDeycv660XVu2fZBFYHMKK45N2TWuuanqgoS1rMpCZBkxH9BqaXFdv6doe1Wa7v2MyjdQ7geqQWbChtgVXBUSPlVFAZDZD',
            'EAABsbCS1iHgBAK2WHx73vqcH3gZCwAegfbzynqkyXagktVLuZAHftL8CpGZB7Fi0NyasujFDEWxtUpMcWwDeycv660XVu2fZBFYHMKK45N2TWuuanqgoS1rMpCZBkxH9BqaXFdv6doe1Wa7v2MyjdQ7geqQWbChtgVXBUSPlVFAZDZD',
            'EAABsbCS1iHgBAMzARqnarr2gMg5sLUfNkDz8AkV0Sm02maHrsiXZAAZBH1mVhDXgXgWr675TvY9DeMGw2tADV8KgigH7dgbOMNgZB1omtkd9w1MhRhZCnNg9Dxr8PzpLMPnUj5NvZARSfbMs3cG0fJmEZCV71yzFp4l7XdbSgpdAZDZD',
            'EAABsbCS1iHgBAMzARqnarr2gMg5sLUfNkDz8AkV0Sm02maHrsiXZAAZBH1mVhDXgXgWr675TvY9DeMGw2tADV8KgigH7dgbOMNgZB1omtkd9w1MhRhZCnNg9Dxr8PzpLMPnUj5NvZARSfbMs3cG0fJmEZCV71yzFp4l7XdbSgpdAZDZD',
        ]
        for x, token in enumerate(list(set(tokens))):
            print(x, token)
            try:

                FacebookAdsApi.init(access_token=token, proxies=proxy)
                user = FBUser(fbid='me')

                businesses = user.get_businesses()
                for business in businesses:
                    faker = Faker()
                    time.sleep(random.randint(10, 100))
                    bm = Business(fbid=business['id'])
                    print('Try to create share')

                    try:
                        bm.create_business_user(params={'email': faker.email(), 'role': 'ADMIN'})
                        share_url = bm.get_pending_users()[0]['invite_link']
                        print(share_url)
                        with open('shared.csv', 'a') as f:
                            f.write(f'{token};{share_url}\n')
                    except Exception as e:
                        print(e)
            except Exception as e:
                print(e)

            # i = 0
            # while True:
            #     n = random.randint(5, 9999)
            #     params = {
            #         'name': f"My Business {n}",
            #         'vertical': 'OTHER',
            #     }
            #     try:
            #         time.sleep(random.randint(10, 120))
            #         print(user.create_business(params=params))
            #         with open('created.txt', 'a') as f:
            #             f.write(f'{x};{token} \n')
            #     except Exception as e:
            #         print(e)
            #         if i == 0:
            #             with open('error.txt', 'a') as f:
            #                 f.write(f'{x};{token} \n')
            #         break
            #     i += 1
