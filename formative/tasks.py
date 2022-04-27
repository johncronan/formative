from celery import shared_task

from .models import Form


@shared_task
def count_forms():
    return Form.objects.count()
