from django.apps import apps
from django.core import mail
from django.template import Template
from django.utils import timezone
from celery import shared_task
import time

from .models import Form
from .utils import send_email, submission_link


EMAILS_PER_SECOND = 10
    
@shared_task
def send_email_for_submissions(model_name, id_values, subject_str, content_str):
    model = apps.get_model(f'formative.{model_name}')
    queryset = model.objects.filter(pk__in=id_values)
    
    subject, content = Template(subject_str), Template(content_str)
    iterator = queryset.iterator()
    batch, form, last_time, done, n = [], None, None, False, 0
    while not done:
        submission = next(iterator, None)
        if not submission: done = True
        else: batch.append(submission)
        
        if len(batch) == EMAILS_PER_SECOND or done:
            if last_time:
                this_time = time.time()
                remaining = last_time + 1 - this_time
                if remaining > 0: time.sleep(remaining)
            last_time = time.time()
            
            with mail.get_connection() as conn:
                for sub in batch:
                    if not form: form = sub._get_form()
                    context = {
                        'submission': sub, 'form': form,
                        'submission_link': submission_link(sub, form)
                    }
                    if sub._submitted: sub._update_context(form, context)
                    n += 1
                    send_email(content, sub._email, subject,
                               context=context, connection=conn)
            batch = []
    return n

@shared_task
def timed_complete_form(form_id, datetime_val):
    try: form = Form.objects.get(id=form_id)
    except Form.DoesNotExist: return
    
    if form.timed_completion() != datetime_val:
        return False # it gets rescheduled on value change, so don't do anything
    
    form.status = Form.Status.COMPLETED
    form.completed = timezone.now()
    form.save()
    return True
