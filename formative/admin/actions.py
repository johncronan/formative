from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib import admin, auth, messages
from django.contrib.admin.utils import NestedObjects
from django.core import exceptions, serializers
from django.db import transaction, IntegrityError
from django.db.models import Count, Max, Sum, Exists, OuterRef
from django.http import HttpResponse, HttpResponseRedirect, StreamingHttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.text import capfirst
from django.shortcuts import get_object_or_404
from urllib.parse import quote
from stream_zip import ZIP_64, stream_zip
from datetime import datetime
from pathlib import Path
import csv, io, os

from ..forms import MoveBlocksAdminForm, EmailAdminForm, FormPluginsAdminForm, \
    UserImportForm, ExportAdminForm
from ..models import Form, FormBlock, SubmissionRecord
from ..tasks import send_email_for_submissions
from ..utils import TabularExport, delete_submission_files, get_current_site


class UserActionsMixin:
    def get_urls(self):
        urls = super().get_urls()
        return [path('import/', self.import_csv)] + urls
    
    def send_password_reset(self, request, queryset):
        for user in queryset:
            form = auth.forms.PasswordResetForm({'email': user.email})
            form.full_clean()
            form.save(**{
                'use_https': request.is_secure(),
                'token_generator': auth.tokens.default_token_generator,
                'from_email': settings.DEFAULT_FROM_EMAIL,
                'email_template_name': 'registration/password_reset_email.html',
                'request': request
            })
        self.message_user(request, 'Password reset emails sent.')
    
    def read_csv(self, site, reader):
        rows = list(reader)
        if not rows: return 'File is empty.', None
        if not rows[0]: return 'File has empty line.', None
        if '@' not in rows[0][0]: rows = rows[1:] # skip header
        data, validator = [], auth.validators.UnicodeUsernameValidator()
        for row in rows:
            if not row: return 'File has empty line.', None
            if '@' not in row[0]:
                return 'Email address must be in first column.', None
            email, *rest = row
            n = len(rest)
            username = f'{email}__{site.id}'
            try: validator(username)
            except exceptions.ValidationError:
                return 'Invalid characters in username.', None
            
            user = {'email': email, 'username': username}
            if n > 0 and rest[0]: user['password'] = rest[0]
            if n > 1 and rest[1]: user['first_name'] = rest[1]
            if n > 2 and rest[2]: user['last_name'] = rest[2]
            data.append(user)
        return None, data
    
    def import_csv(self, request):
        User, err = auth.get_user_model(), None
        if request.method == 'POST':
            site = get_current_site(request)
            
            csv_file = request.FILES['csv_file']
            reader = csv.reader(io.TextIOWrapper(csv_file, encoding='utf-8'))
            err, user_data = self.read_csv(site, reader)
            if not err:
                skipped = 0
                for entry in user_data:
                    password = entry.pop('password', None)
                    u = User(site=site, **entry)
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


class NonPolymorphicNestedObjects(NestedObjects):
    def related_objects(self, related_model, related_fields, objs):
        qs = super().related_objects(related_model, related_fields, objs)
        # somehow, the dumpdata management command doesn't have this problem
        if hasattr(qs, 'non_polymorphic'): return qs.non_polymorphic()
        return qs


class FormActionsMixin:
    def change_view(self, request, object_id, **kwargs):
        action, kwargs = None, {}
        if '_publish' in request.POST: action = 'publish'
        elif '_unpublish_confirmed' in request.POST: action = 'unpublish'
        
        if not action: return super().change_view(request, object_id, **kwargs)
        
        obj = self.get_object(request, object_id)
        getattr(obj, action)(**kwargs)
        
        self.log_change(request, obj, action + 'ed')
        return HttpResponseRedirect(request.get_full_path())
    
    def log_change(self, request, obj, message):
        if not message: return
        return super().log_change(request, obj, message)
    
    def response_change(self, request, obj):
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'media': self.media,
            'object': obj,
            'title': 'Confirmation'
        }
#        if '_publish' in request.POST:
#            return TemplateResponse(request, 'admin/publish_confirmation.html',
#                                    context)
        if '_unpublish' in request.POST:
            subs = []
            if obj.status != Form.Status.DRAFT:
                qs = obj.model.objects.all()
                if obj.item_model:
                    qs = qs.annotate(num_items=Count('_item'))
                    subs = qs.values_list('_email', 'num_items')
                else: subs = qs.values_list('_email')
            context['submissions'] = subs
            model_name = obj.model._meta.model_name
            context['link_name'] = f'admin:formative_{model_name}_changelist'
            request.current_app = self.admin_site.name
            template_name = 'admin/formative/unpublish_confirmation.html'
            return TemplateResponse(request, template_name, context)
        
        return super().response_change(request, obj)
    
    @admin.action(description='Enable/disable a plugin')
    def form_plugins(self, request, queryset):
        if '_submit' in request.POST:
            which, plugin, n = request.POST['which'], request.POST['plugin'], 0
            for form in queryset:
                if plugin not in form.get_available_plugins(): continue
                if which == 'enable': form.add_plugins([plugin])
                else: form.remove_plugins([plugin])
                form.save()
                n += 1
            
            msg = f"{capfirst(which)}d plugin '{plugin}' for {n} forms."
            if n: self.message_user(request, msg, messages.SUCCESS)
            
            return HttpResponseRedirect(request.get_full_path())
        
        template_name = 'admin/formative/form_plugins.html'
        request.current_app = self.admin_site.name
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta, 'media': self.media,
            'forms': queryset, 'title': 'Enable or Disable Plugin',
            'form': FormPluginsAdminForm()
        }
        return TemplateResponse(request, template_name, context)
    
    def form_objects(self, queryset):
        collector = NonPolymorphicNestedObjects(using='default')
        collector.collect(queryset)
        models = serializers.sort_dependencies([(None, collector.data.keys())])
        return [ obj for cls in models for obj in collector.data[cls]
                 if cls._meta.app_label == 'formative' ]
    
    @admin.action(description='Export selected forms as JSON')
    def export_json(self, request, queryset):
        response = HttpResponse(content_type='text/javascript')
        serializers.serialize('json', self.form_objects(queryset),
                              use_natural_foreign_keys=True,
                              use_natural_primary_keys=True, stream=response)
        
        if len(queryset) == 1: filename = f'{queryset[0].slug}_export.json'
        else: filename = f'{queryset[0].program.slug}_selected__export.json'
        disp = f"attachment; filename*=UTF-8''" + quote(filename)
        response['Content-Disposition'] = disp
        return response
    
    @admin.action(description='Copy a form')
    def duplicate(self, request, queryset):
        form = queryset[0]
        if '_duplicate' in request.POST:
            new = None
            with transaction.atomic():
                form.slug = request.POST['new_slug']
                form.name = request.POST['new_name']
                form.save()
                
                related = self.form_objects(Form.objects.filter(pk=form.pk))
                new = serializers.serialize('json', related,
                                            use_natural_foreign_keys=True,
                                            use_natural_primary_keys=True)
                transaction.set_rollback(True)
            
            with transaction.atomic():
                for obj in serializers.deserialize('json', new):
                    if obj.object._meta.model_name == 'form':
                        obj.object.status = Form.Status.DRAFT
                    obj.save()
            
            self.message_user(request, 'Form copied.', messages.SUCCESS)
            return HttpResponseRedirect(request.get_full_path())
        
        name_maxlen = Form._meta.get_field('name').max_length
        class FormCopyForm(forms.Form):
            new_slug = forms.SlugField(allow_unicode=True,
                                       label='New identifier')
            new_name = forms.CharField(max_length=name_maxlen)
        
        template_name = 'admin/formative/copy_form.html'
        request.current_app = self.admin_site.name
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta, 'media': self.media, 'title': 'Copy Form',
            'allowed': len(queryset) == 1, 'program_form': form,
            'form': FormCopyForm(initial={'new_slug': form.slug})
        }
        return TemplateResponse(request, template_name, context)


class FormBlockActionsMixin:
    @admin.action(description='Move to different page')
    def move_blocks_action(self, request, queryset):
        if '_move' in request.POST:
            page, n = request.POST['page'], 0
            blocks, cur_page = queryset[0].form.blocks, queryset[0].page
            last_rank_q = blocks.filter(page=cur_page).aggregate(r=Max('_rank'))
            last_rank = last_rank_q['r']
            for block in cur_page and queryset.order_by('_rank') or []:
                block = FormBlock.objects.get(pk=block.pk) # clear side effects;
                block._rank = last_rank
                block.save() # it's now at the end of its page; and
                block.page, block._rank = page, None # then move to the new one,
                block.save() # so that the others on the old page are left sorted
                n, last_rank = n + 1, last_rank - 1
            
            msg = f'Moved {n} blocks to page {page}'
            if n: self.message_user(request, msg, messages.SUCCESS)
            
            return HttpResponseRedirect(request.get_full_path())
        
        template_name = 'admin/formative/move_page.html'
        request.current_app = self.admin_site.name
        min_page = max(block.min_allowed_page() for block in queryset)
        last_page = queryset[0].form.blocks.aggregate(p=Max('page'))['p']
        max_page = min(block.max_allowed_page(last_page) for block in queryset)
        new = max_page == last_page
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta, 'media': self.media,
            'blocks': queryset, 'title': 'Move Blocks',
            'movable': queryset[0].form.status == Form.Status.DRAFT,
            'form': MoveBlocksAdminForm(max_page,
                                        min_page=min_page, new_page=new),
        }
        return TemplateResponse(request, template_name, context)


class SubmissionActionsMixin:
    @admin.action(description='Send an email to applicants')
    def send_email(self, request, queryset):
        if '_send' in request.POST:
            send_email_for_submissions.delay(
                queryset.model._meta.model_name,
                list(queryset.values_list('pk', flat=True)),
                request.POST['subject'], request.POST['content']
            )
            msg = f'Email sending started for {queryset.count()} recipients.'
            self.message_user(request, msg, messages.SUCCESS)
            
            return HttpResponseRedirect(request.get_full_path())
        
        form = queryset[0]._get_form()
        template_name = 'admin/formative/email_applicants.html'
        request.current_app = self.admin_site.name
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta, 'media': self.media,
            'submissions': queryset, 'title': 'Email Applicants',
            'form': EmailAdminForm(form=form),
            'email_templates': form.email_templates(),
        }
        return TemplateResponse(request, template_name, context)
    
    @admin.action(description='Export submissions as CSV')
    def export_csv(self, request, queryset):
        program_form = queryset.model._get_form()
        if '_export' in request.POST:
            args = { k: request.POST[k] for k in request.POST
                     if k.startswith('block_') or k.startswith('collection_')
                        or k.startswith('cfield_') }
            export = TabularExport(program_form, queryset, **args)
            filename = f'{program_form.slug}_export_selected.csv'
            return export.csv_response(filename, queryset)
        
        template_name = 'admin/formative/export_submissions.html'
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta, 'media': self.media,
            'submissions': queryset, 'title': 'Export Submissions',
            'form': ExportAdminForm(program_form=program_form)
        }
        return TemplateResponse(request, template_name, context)
    
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
        
        obj_dir = os.path.join(settings.MEDIA_ROOT, str(obj._id))
        submit_file = os.path.join(obj_dir, 'submitted')
        if action == 'submit':
            if not rec: obj._get_form().submit_submission(obj)
            else:
                obj._submit()
                rec.deleted = False
                
                if os.path.isdir(obj_dir): Path(submit_file).touch()
        else:
            obj._submitted = None
            obj.save()
            if rec: rec.deleted = True
            
            if os.path.isdir(obj_dir):
                if os.path.exists(submit_file): os.remove(submit_file)
        if rec: rec.save()
        
        self.log_change(request, obj, action + 'ted')
        return HttpResponseRedirect(request.get_full_path())
    
    def log_change(self, request, obj, message):
        if not message: return
        return super().log_change(request, obj, message)
    
    def response_change(self, request, obj):
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'media': self.media,
            'object': obj,
            'title': 'Confirmation'
        }
        if '_submit' in request.POST or '_unsubmit' in request.POST:
            template_name = 'admin/formative/submit_confirmation.html'
            request.current_app = self.admin_site.name
            if '_submit' in request.POST: context['submit'] = True
            else: context['unsubmit'] = True
            
            return TemplateResponse(request, template_name, context)
        
        return super().response_change(request, obj)
    
    def changelist_view(self, request, **kwargs):
        context = {
            **self.admin_site.each_context(request), 'title': 'Manage Files',
            'opts': self.model._meta, 'media': self.media
        }
        files_type = SubmissionRecord.RecordType.FILES
        
        if '_manage_submit' in request.POST:
            target = request.POST['manage_action']
            form = self.model._get_form()
            sr = SubmissionRecord.objects.all()
            
            qs = sr.filter(program=form.program, form=form.slug, deleted=False,
                           type=SubmissionRecord.RecordType.FILES)
            q1 = self.model.objects.filter(_id=OuterRef('submission'))
            q2 = sr.filter(submission=OuterRef('submission'), deleted=False,
                           type=SubmissionRecord.RecordType.SUBMISSION)
            if target == 'draft': qs = qs.exclude(Exists(q2)).filter(Exists(q1))
            elif target == 'deleted': qs = qs.exclude(Exists(q1))
            
            delete_submission_files(qs) # TODO: should skip if item still exists
            qs.update(deleted=True)
            self.message_user(request, 'Files deleted.', messages.SUCCESS)
            return HttpResponseRedirect(request.get_full_path())
        
        if '_manage_files' in request.POST:
            template_name = 'admin/formative/manage_files.html'
            request.current_app = self.admin_site.name
            
            form = self.model._get_form()
            context['program_form'] = form
            sr = SubmissionRecord.objects.all()
            aggs = {'size': Sum('number'), 'count': Count('*')}
            qs = sr.filter(program=form.program, form=form.slug,
                           type=files_type, deleted=False)
            context['total'] = qs.aggregate(**aggs)
            
            submission_type = SubmissionRecord.RecordType.SUBMISSION
            model_subq = self.model.objects.filter(_id=OuterRef('submission'))
            subq = sr.filter(submission=OuterRef('submission'),
                             type=submission_type, deleted=False)
            draft = qs.exclude(Exists(subq)).filter(Exists(model_subq))
            context['draft'] = draft.aggregate(**aggs)
            
            deleted = qs.exclude(Exists(model_subq))
            context['deleted'] = deleted.aggregate(**aggs)
            
            return TemplateResponse(request, template_name, context)
        
        return super().changelist_view(request, **kwargs)
    
    @admin.action(description='Download submission files')
    def download_files(self, request, queryset):
        template_name = 'admin/formative/files_download.html'
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta, 'media': self.media,
            'submissions': queryset, 'title': 'Download Submission Files',
            'action': reverse('admin:formative_files_download',
                              args=(self.model._get_form().pk,),
                              current_app=self.admin_site.name)
        }
        return TemplateResponse(request, template_name, context)


# separate URL for download so that we can disable proxy_buffering in nginx conf
def download_view(request, form_id):
    form = get_object_or_404(Form, id=form_id)
    item_model = form.item_model
    
    def files(selected, item_model):
        items = item_model.objects.filter(_submission__in=selected)
        
        modified, last_sub = datetime.now(), None
        for item in items.exclude(_file='').order_by('_submission'):
            def file_data(path):
                CHUNK_SIZE = 8192
                with open(path, 'rb') as f:
                    while True:
                        data = f.read(CHUNK_SIZE)
                        if not data: break
                        yield data
            
            if last_sub is None or last_sub != item._submission_id:
                sub_id = str(item._submission_id)
                rel_path = os.path.join(sub_id, 'id.txt')
                full_path = os.path.join(settings.MEDIA_ROOT, rel_path)
                if os.path.exists(full_path):
                    with open(full_path, 'rb') as f:
                        yield rel_path, modified, 0o644, ZIP_64, [f.read()]
                rel_path = os.path.join(sub_id, 'submitted')
                full_path = os.path.join(settings.MEDIA_ROOT, rel_path)
                if os.path.exists(full_path):
                    yield rel_path, modified, 0o644, ZIP_64, [b'']
            last_sub = item._submission_id
            
            data = file_data(item._file.path)
            yield item._file.name, modified, 0o644, ZIP_64, data
    
    selected = request.POST.getlist('_selected_action')
    response = StreamingHttpResponse(stream_zip(files(selected, item_model)),
                                     content_type='application/zip')
    
    filename = f'{form.slug}_files.zip'
    disp = f"attachment; filename*=UTF-8''" + quote(filename)
    response['Content-Disposition'] = disp
    return response
