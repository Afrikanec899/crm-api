import logging
from typing import Any, Dict

from project.celery_app import app

from ..models import Contact
from ..models.core import Campaign

logger = logging.getLogger(__name__)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 1})
def process_contact_task(self, data: Dict[Any, Any]) -> None:
    visit_id = data.pop('visit_id', None)
    if visit_id:
        try:
            contact = Contact.objects.get(visit_id=visit_id)
            Contact.update(pk=contact.id, **data)
        except Contact.DoesNotExist:
            Contact.create(visit_id=visit_id, **data)
    else:
        Contact.create(**data)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 1})
def process_contact_postback_task(self, data: Dict[Any, Any]) -> None:
    contact = Contact.objects.filter(visit_id=data.pop('visit_id')).first()
    campaign = Campaign.objects.filter(symbol=data.pop('campaign_id')).first()
    # if not contact or not campaign:
    #     logger.error('contact or campaign not found', exc_info=True)
    # else:
    if contact and campaign:
        contact.has_leads = True
        contact.postback_data = data
        contact.save()
