from django.conf import settings
from django.contrib import admin, auth, messages
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Max
from django.http import HttpResponseRedirect
from django.template import Template
from django.template.response import TemplateResponse
from django.urls import path
import time, csv, io

from ..forms import MoveBlocksAdminForm, EmailAdminForm, UserImportForm
from ..models import Form, FormBlock, SubmissionRecord
from ..utils import send_email


@admin.action(description='Move to different page')
def move_blocks_action(modeladmin, request, queryset):
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
    request.current_app = modeladmin.admin_site.name
    min_page = max(block.min_allowed_page() for block in queryset)
    last_page = queryset[0].form.blocks.aggregate(p=Max('page'))['p']
    max_page = min(block.max_allowed_page(last_page) for block in queryset)
    new = max_page == last_page
    context = {
        **modeladmin.admin_site.each_context(request),
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
    request.current_app = modeladmin.admin_site.name
    context = {
        **modeladmin.admin_site.each_context(request),
        'opts': modeladmin.model._meta,
        'media': modeladmin.media,
        'submissions': queryset,
        'form': EmailAdminForm(form=form),
        'email_templates': form.email_templates(),
        'title': 'Email Applicants'
    }
    return TemplateResponse(request, template_name, context)


class UserActionsMixin:
    def get_urls(self):
        urls = super().get_urls()
        return [path('import/', self.import_csv)] + urls
    
    def send_password_reset(self, request, queryset):
        for user in queryset:
            form = auth.forms.PasswordResetForm({'email': user.email})
            form.full_clean()
            form.save({
                'use_https': request.is_secure(),
                'token_generator': auth.tokens.default_token_generator,
                'from_email': settings.DEFAULT_FROM_EMAIL,
                'email_template_name': 'registration/password_reset_email.html',
                'request': request
            })
        self.message_user(request, 'Password reset emails sent.')
    
    def read_csv(self, reader):
        rows = list(reader)
        if not rows: return 'File is empty.', None
        if not rows[0]: return 'File has empty line.', None
        if '@' not in rows[0][0]: rows = rows[1:] # skip header
        data, validator = [], auth.validators.UnicodeUsernameValidator()
        for row in rows:
            if not row: return 'File has empty line.', None
            if '@' not in row[0]:
                return 'Email address must be in first column.', None
            n = len(row)
            if n < 2: return 'Required columns: email, username.', None
            email, username, *rest = row
            if not username: return 'Username is required.', None
            try: validator(username)
            except ValidationError:
                return 'Invalid characters in username.', None
            
            user = {'email': email, 'username': username}
            if n > 2 and row[2]: user['password'] = row[2]
            if n > 3 and row[3]: user['first_name'] = row[3]
            if n > 4 and row[4]: user['last_name'] = row[4]
            data.append(user)
        return None, data
    
    def import_csv(self, request):
        err = None
        if request.method == 'POST':
            csv_file = request.FILES['csv_file']
            reader = csv.reader(io.TextIOWrapper(csv_file, encoding='utf-8'))
            err, user_data = self.read_csv(reader)
            if not err:
                skipped = 0
                for entry in user_data:
                    password = entry.pop('password', None)
                    u = User(**entry)
                    if not password: u.set_unusable_password()
                    else: u.set_password(password)
                    try: u.save()
                    except IntegrityError: skipped += 1
                
                msg = 'Users created.'
                if skipped: msg += f' ({skipped} user(s) already existed.)'
                self.message_user(request, msg)
                return HttpResponseRedirect('../')
        
        form = UserImportForm(request.POST, request.FILES)
        form.full_clean()
        if err: form.add_error(None, err)
        
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta, 'media': self.media,
            'form': form, 'title': 'Import Users CSV'
        }
        template_name = 'admin/formative/import_users.html'
        return TemplateResponse(request, template_name, context)


class FormActionsMixin:
    def change_view(self, request, object_id, **kwargs):
        action, kwargs = None, {}
        if '_publish' in request.POST: action = 'publish'
        elif '_unpublish_confirmed' in request.POST: action = 'unpublish'
        
        if not action: return super().change_view(request, object_id, **kwargs)
        
        obj = self.get_object(request, object_id)
        getattr(obj, action)(**kwargs)
        
        return HttpResponseRedirect(request.get_full_path())
    
    def response_change(self, request, obj):
        subs = []
        if obj.status != Form.Status.DRAFT:
            qs = obj.model.objects.all()
            if obj.item_model:
                qs = qs.annotate(num_items=Count('_item'))
                subs = qs.values_list('_email', 'num_items')
            else: subs = qs.values_list('_email')
        
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'media': self.media,
            'object': obj,
            'submissions': subs,
            'title': 'Confirmation'
        }
#        if '_publish' in request.POST:
#            return TemplateResponse(request, 'admin/publish_confirmation.html',
#                                    context)
        if '_unpublish' in request.POST:
            request.current_app = self.admin_site.name
            template_name = 'admin/formative/unpublish_confirmation.html'
            return TemplateResponse(request, template_name, context)
        
        return super().response_change(request, obj)


class SubmissionActionsMixin:
    def change_view(self, request, object_id, **kwargs):
        action, kwargs = None, {}
        if '_submit_confirmed' in request.POST: action = 'submit'
        elif '_unsubmit_confirmed' in request.POST: action = 'unsubmit'
        
        if not action:
            kwargs['extra_context'] = {'model_is_submission': True}
            return super().change_view(request, object_id, **kwargs)
        
        obj = self.get_object(request, object_id)
        rec, rtype = None, SubmissionRecord.RecordType.SUBMISSION
        try: rec = SubmissionRecord.objects.get(submission=obj._id, type=rtype)
        except SubmissionRecord.DoesNotExist: pass
        
        if action == 'submit':
            if not rec: obj._get_form().submit_submission(obj)
            else:
                obj._submit()
                rec.deleted = False
        else:
            obj._submitted = None
            obj.save()
            if rec: rec.deleted = True
        if rec: rec.save()
        return HttpResponseRedirect(request.get_full_path())
    
    def response_change(self, request, obj):
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'media': self.media,
            'object': obj,
            'title': 'Confirmation'
        }
        template_name = 'admin/formative/submit_confirmation.html'
        if '_submit' in request.POST or '_unsubmit' in request.POST:
            request.current_app = self.admin_site.name
            if '_submit' in request.POST: context['submit'] = True
            else: context['unsubmit'] = True
            
            return TemplateResponse(request, template_name, context)
        
        return super().response_change(request, obj)
