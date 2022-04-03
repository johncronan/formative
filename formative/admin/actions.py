from django.contrib import admin, messages
from django.core import mail
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.template import Template
from django.template.response import TemplateResponse
import time

from ..forms import MoveBlocksAdminForm, EmailAdminForm
from ..models import Form, FormBlock
from ..utils import send_email


@admin.action(description='Move to different page')
def move_blocks_action(modeladmin, request, queryset):
    from .formative import site
    
    if '_move' in request.POST:
        page, n = request.POST['page'], 0
        blocks, cur_page = queryset[0].form.blocks, queryset[0].page
        last_rank = blocks.filter(page=cur_page).aggregate(r=Max('_rank'))['r']
        for block in queryset.order_by('_rank'):
            block = FormBlock.objects.get(pk=block.pk) # clear side effects;
            block._rank = last_rank
            block.save() # it's now at the end of its page;
            block.page, block._rank = page, None # and then move to the new one,
            block.save() # so that the others on the old page are left sorted
            n, last_rank = n + 1, last_rank - 1
        
        msg = f'Moved {n} blocks to page {page}'
        modeladmin.message_user(request, msg, messages.SUCCESS)
        
        return HttpResponseRedirect(request.get_full_path())
    
    template_name = 'admin/formative/move_page.html'
    request.current_app = site.name
    min_page = max(block.min_allowed_page() for block in queryset)
    last_page = queryset[0].form.blocks.aggregate(p=Max('page'))['p']
    max_page = min(block.max_allowed_page(last_page) for block in queryset)
    new = max_page == last_page
    context = {
        **site.each_context(request),
        'opts': modeladmin.model._meta,
        'media': modeladmin.media,
        'blocks': queryset,
        'movable': queryset[0].form.status == Form.Status.DRAFT,
        'form': MoveBlocksAdminForm(max_page, min_page=min_page, new_page=new),
        'title': 'Move Blocks'
    }
    return TemplateResponse(request, template_name, context)


EMAILS_PER_SECOND = 10

@admin.action(description='Send an email to applicants')
def send_email_action(modeladmin, request, queryset):
    from .formative import site
    
    if '_send' in request.POST:
        # TODO: celery task
        subject = Template(request.POST['subject'])
        content = Template(request.POST['content'])
        
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
        
        msg = f'Emails sent to {n} recipients.'
        modeladmin.message_user(request, msg, messages.SUCCESS)
        
        return HttpResponseRedirect(request.get_full_path())
    
    form = queryset[0]._get_form()
    template_name = 'admin/formative/email_applicants.html'
    request.current_app = site.name
    context = {
        **site.each_context(request),
        'opts': modeladmin.model._meta,
        'media': modeladmin.media,
        'submissions': queryset,
        'form': EmailAdminForm(form=form),
        'email_templates': form.email_templates(),
        'title': 'Email Applicants'
    }
    return TemplateResponse(request, template_name, context)

