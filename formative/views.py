from django.http import HttpResponse, HttpResponseRedirect, Http404, \
    HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django import forms
from django.db import transaction
from django.db.models import F, Min
from django.forms.models import modelform_factory, modelformset_factory
from django.views import generic
import itertools
import os

from .models import Program, Form, FormBlock, CustomBlock, CollectionBlock, \
    SubmissionRecord, SubmissionItem
from .forms import OpenForm, SubmissionForm, ItemFileForm, ItemsFormSet, \
    ItemsForm
from .filetype import FileType
from .signals import submission_handle_submit
from .utils import delete_file, get_file_extension, get_tooltips


class ProgramIndexView(generic.ListView):
    template_name = 'formative/index.html'
    context_object_name = 'programs'
    
    def get_queryset(self):
        return Program.objects.filter(hidden=False)


class ProgramView(generic.DetailView):
    model = Program
    template_name = 'formative/program.html'
    slug_field = 'slug'


class ProgramFormMixin(generic.edit.FormMixin):
    def dispatch(self, request, *args, **kwargs):
        form = get_object_or_404(Form.objects.select_related('program'),
                                 program__slug=self.kwargs['program_slug'],
                                 slug=self.kwargs['form_slug'])
        self.program_form = form
        
        if self.program_form.hidden(): # and 'sid' not in kwargs:
            key, params = self.program_form.access_enable(), self.request.GET
            template = self.template_name
            if 'thanks' not in template and 'continue' not in template:
                if not key or 'access' not in params or params['access'] != key:
                    kwargs = {'slug': self.program_form.program.slug}
                    return HttpResponseRedirect(reverse('program',
                                                        kwargs=kwargs))
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not self.program_form.model: raise Http404()
        
        context['program_form'] = self.program_form
        context['tooltips'] = get_tooltips
        return context


class ProgramFormView(ProgramFormMixin, generic.edit.ProcessFormView,
                      generic.base.TemplateResponseMixin):
    template_name = 'formative/form.html'
    form_class = OpenForm
    context_object_name = 'program_form'
    
    def get_success_url(self):
        return reverse('form_continue', kwargs={
            'program_slug': self.program_form.program.slug,
            'form_slug': self.program_form.slug,
        })
    
    def form_valid(self, form):
        model = self.program_form.model
        self.object, created = model.objects.get_or_create(
            _email=form.cleaned_data['email']
        )
        
        if not self.object._submitted: template = 'continue'
        else: template = 'confirmation'
        
        self.object._send_email(form=self.program_form, name=template)
        return super().form_valid(form)


class SubmissionView(ProgramFormMixin, generic.UpdateView):
    template_name = 'formative/submission.html'
    context_object_name = 'submission'
    first_page = False
    
    def dispatch(self, request, *args, **kwargs):
        self.page = None
        if 'page' in self.kwargs: self.page = self.kwargs['page']
        if self.first_page: self.page = 1

        self.skipped, self.blocks_by_name, self.formsets = {}, {}, None
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_object(self):
        submission = get_object_or_404(self.program_form.model,
                                       _id=self.kwargs['sid'])
        self.program_form.item_model
        
        return submission

    def get_form(self):
        fields, widgets, customs, stocks = [], {}, {}, {}

        self.query = self.program_form.visible_blocks()
        if self.page: self.query = self.query.filter(page=self.page)
        # having the form for the final GET simplifies templates for review step
        elif self.request.method == 'POST': self.query = self.query.none()

        blocks_checked, enabled = {}, []
        skipped_pages = self.object._skipped[:self.page or self.object._valid]
        skipped_ids = dict.fromkeys(itertools.chain(*skipped_pages), True)
        
        for block in self.query:
            d_id = block.dependence_id
            if d_id and d_id not in blocks_checked:
                # when we encounter a new block that some field is dependent on,
                # if it isn't among the blocks that were already _skipped,
                # enable this page's fields with a dependency matching the value
                if d_id not in skipped_ids:
                    b = FormBlock.objects.get(id=d_id)
                    if b.block_type() == 'stock':
                        stock = b.stock
                        values = { n: getattr(self.object, stock.field_name(n))
                                   for n in stock.widget_names() }
                        v = b.stock.conditional_value(**values)
                    elif b.block_type() == 'custom':
                        v = b.conditional_value(getattr(self.object, b.name))
                    else: # collection
                        v = bool(self.object._items.filter(_block=b.pk))
                    
                    enabled += b.enabled_blocks(v, self.page)
                blocks_checked[d_id] = True
            
            if d_id and block.id not in enabled:
                self.skipped[block.id] = block
                continue
            
            for name, field in block.fields():
                fields.append(name)
                if block.block_type != 'collection':
                    self.blocks_by_name[name] = block
                
                if block.block_type() == 'custom':
                    customs[name] = block
                    if block.type == CustomBlock.InputType.CHOICE:
                        widgets[name] = forms.RadioSelect
                    elif block.type == CustomBlock.InputType.BOOLEAN:
                        widgets[name] = forms.CheckboxInput
                elif block.block_type() == 'stock':
                    stocks[name] = block.stock
                    for name in block.stock.widget_names():
                        field_name = block.stock.field_name(name)
                        if (widget := block.stock.form_widget(name)):
                            widgets[field_name] = widget
        
        # this reuses self.query:
        self.formsets = self.get_formsets(enabled)
        
        def callback(model_field, **kwargs):
            name = model_field.name
            if name in customs:
                return customs[name].form_field(model_field, **kwargs)
            return model_field.formfield(**kwargs)
        
        form_class = modelform_factory(self.program_form.model,
                                       form=SubmissionForm,
                                       formfield_callback=callback,
                                       fields=fields, widgets=widgets)
        
        f = form_class(custom_blocks=customs, stock_blocks=stocks,
                       program_form=self.program_form, page=self.page,
                       **self.get_form_kwargs())
        return f
    
    def get_formsets(self, enabled):
        formsets = {}
        for block in self.query:
            if block.block_type() != 'collection': continue
            if block.dependence and block.id not in enabled: continue
            
            kwargs = self.get_form_kwargs()
            kwargs.pop('prefix')
            kwargs.pop('instance')

            item_model = self.program_form.item_model
            queryset = self.object._items.filter(_block=block.pk)
            queryset = queryset.exclude(_file='', _filesize__gt=0)
            
            extra = 0
            if block.fixed and not queryset:
                extra = block.num_choices()
                choices = [ {block.name1: c} for c in block.fixed_choices() ]
                kwargs['initial'] = choices
            
            fields = block.collection_fields()
            if block.fixed and queryset:
                if self.request.method == 'POST': fields = fields[1:]
            
            FormSet = modelformset_factory(item_model,
                                           formset=ItemsFormSet, form=ItemsForm,
                                           fields=fields,
                                           # TODO: use edit_only once available
                                           max_num=extra, can_delete=False,
                                           extra=extra, validate_max=False)

            formset = FormSet(prefix=f'items{block.pk}', queryset=queryset,
                              block=block, instance=self.object, **kwargs)
            formsets[block.pk] = formset
        
        return formsets
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context['program_form']
        
        context['field_labels'] = form.field_labels()
        args, items = {'page': self.page, 'skip': self.skipped.keys()}, {}
        for item in form.visible_items(self.object, **args):
            if item._block not in items: items[item._block] = []
            items[item._block].append(item)
        context.update(visible_items=items, formsets=self.formsets)
        
        if self.page:
            context.update({
                'page': self.page,
                'prev_page': self.page > 1 and self.page - 1 or None,
                'visible_blocks': form.visible_blocks(**args)
            })
        else: context['prev_page'] = form.num_pages()
        
        return context
    
    def reset_skipped(self, ids=None):
        # when resetting the results of later pages that have been invalidated,
        # we haven't yet encountered these blocks, so we have to look them up:
        if ids: skipped = self.program_form.blocks.filter(id__in=ids)
        else: skipped = self.skipped.values()
        
        rec = None
        if self.program_form.item_model:
            items = self.object._items.filter(_block__in=list(self.skipped))
            if items.exclude(_file='').exists():
                rec = SubmissionRecord.objects.get(
                    submission=self.object.pk,
                    type=SubmissionRecord.RecordType.FILES
                )
        for block in skipped:
            if block.block_type() == 'collection':
                items = self.object._items.filter(_block=block.pk)
                for item in items:
                    if item._file:
                        delete_file(item._file)
                        rec.number = F('number') - item._filesize
                        rec.save()
                        rec.refresh_from_db() # clear the decrementer
                items.delete() # bulk is ok for ranked, because it's all of them
            else:
                val = None
                if block.block_type() == 'custom': val = block.default_value()
                for name, f in block.fields():
                    setattr(self.object, name, val)
    
    def new_page_valid(self, form):
        changed = [ self.blocks_by_name[n].id for n in form.changed_data ]
        if not changed: return self.object._valid # don't update _valid
        
        query = FormBlock.objects.filter(id__in=changed)
        query = query.annotate(pagemin=Min('dependent__page'))
        query = query.aggregate(min_pagemin=Min('pagemin'))
        
        if not query['min_pagemin']: return self.object._valid
        return query['min_pagemin'] - 1
    
    def form_valid(self, form):
        if not self.page:
            res = submission_handle_submit.send(self.program_form,
                                                submission=self.object)
            if res and res[0][1]: return res[0][1]
            
            # the draft submission will now be marked as submitted
            self.program_form.submit_submission(self.object)
            self.object._send_email(form=self.program_form, name='confirmation')
            
            return HttpResponseRedirect(reverse('form_thanks',
                                                kwargs=self.url_args(id=False)))
        
        self.object = form.save(commit=False)
        
        if self.page <= self.object._valid:
            self.object._valid = self.new_page_valid(form)
        else: self.object._valid = self.page
        
        if self.object._valid < len(self.object._skipped):
            self.object._skipped = self.object._skipped[:self.object._valid]
        
        if len(self.object._skipped) < self.page:
            # assumes only by 1; TODO: skipping an entire page or multiple pages
            self.object._skipped.append([])
        
        can_ignore = [ k for k, v in self.skipped.items()
                       if v.block_type() != 'custom' or not v.default_value() ]
        self.object._skipped[self.page-1] = can_ignore
        self.reset_skipped()
        
        for formset in self.formsets.values():
            block = formset.block
            
            if block.fixed and not formset.get_queryset():
                forms, choices = {}, block.fixed_choices()
                for form in formset.forms:
                    rank_key = form.add_prefix('_rank')
                    if rank_key in form.data:
                        forms[int(form.data[rank_key])] = form
                
                # create the items in the given order
                for i in range(block.num_choices()):
                    if i in forms:
                        if form.cleaned_data[block.name1] not in choices:
                            continue # form tampering
                        item = forms[i].save(commit=False)
                        item._block = block.pk
                        item._collection = block.name
                        item._submission = self.object
                        item.save()
            
            else: formset.save()
            
            items = self.object._items.filter(_block=formset.block.pk)
            failed_uploads = items.filter(_file='', _filesize__gt=0)
            # must do one at a time, because of the ranked model:
            for item in failed_uploads: item.delete()
            
            types = {}
            for item in items:
                if 'type' not in item._filemeta: continue
                filetype = FileType.by_type(item._filemeta['type'])()
                if filetype not in types: types[filetype] = []
                types[filetype].append(item)
                
            for filetype, items in types.items(): filetype.submitted(items)
        
        self.object.save()
        return HttpResponseRedirect(self.get_success_url())
    
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        form = self.get_form()
        formsets = self.formsets
        if form.is_valid() and all(f.is_valid() for f in formsets.values()):
            return self.form_valid(form)
        else:
            return self.form_invalid(form)
    
    def url_args(self, id=True):
        args = {
            'program_slug': self.program_form.program.slug,
            'form_slug': self.program_form.slug
        }
        if id: args['sid'] = self.object._id
        return args
        
    def render_to_response(self, context):
        form = self.program_form
        
        if self.object._submitted:
            if self.page or not form.review_after_submit():
                url = reverse('form_thanks', kwargs=self.url_args(id=False))
                return HttpResponseRedirect(url)
            else: context['submitted'] = True
        
        if self.page and form.status != Form.Status.ENABLED:
            if not form.extra_time():
                if self.object._valid == form.num_pages():
                    url = reverse('submission_review', kwargs=self.url_args())
                else: url = reverse('program',
                                    kwargs={'slug': form.program.slug})
                return HttpResponseRedirect(url)
        
        if (
            self.page and context['page'] <= self.object._valid + 1
            or self.object._valid == form.num_pages() or self.object._submitted
        ):
            return super().render_to_response(context)
        
        # tried to skip ahead - go back to the last page that can be displayed
        name, args = 'submission_page', self.url_args()
        if self.object._valid: args['page'] = self.object._valid + 1
        else: name = 'submission'
        
        return HttpResponseRedirect(reverse(name, kwargs=args))
    
    def get_success_url(self):
        kwargs = self.url_args() 

        name = 'submission_page'
        if 'continue' in self.request.POST:
            if self.page == self.program_form.num_pages(): # we're done
                name = 'submission_review'
            else: kwargs['page'] = self.page + 1
        else:
            if self.page == 1: name = 'submission'
            else: kwargs['page'] = self.page
        
        return reverse(name, kwargs=kwargs)


class SubmissionBase(generic.View):
    def get_context_data(self, **kwargs):
        context = kwargs
        
        context['form_block'] = self.block
        return context
    
    def dispatch(self, request, *args, **kwargs):
        form = get_object_or_404(Form,
                                 program__slug=self.kwargs['program_slug'],
                                 slug=self.kwargs['form_slug'])
        self.program_form = form
        if not self.program_form.item_model: raise Http404()
        
        if form.status == Form.Status.DRAFT: return HttpResponseBadRequest()
        
        self.submission = get_object_or_404(self.program_form.model,
                                            _id=self.kwargs['sid'])
        if self.submission._submitted: return HttpResponseBadRequest()
        
        return super().dispatch(request, *args, **kwargs)


class SubmissionItemCreateView(SubmissionBase,
                               generic.base.TemplateResponseMixin):
    template_name = 'formative/collection_items_new.html'
    http_method_names = ['post']
    
    def get_form(self, **kwargs):
        if not self.block.has_file: return forms.Form(data={})
        return ItemFileForm(block=self.block, data=kwargs)
    
    def get_formset(self, ids):
        FormSet = modelformset_factory(self.program_form.item_model,
                                       formset=ItemsFormSet, form=ItemsForm,
                                       fields=self.block.collection_fields(),
                                       max_num=0, can_delete=False)
        
        queryset = self.submission._items.filter(_block=self.block.pk)
        queryset = queryset.filter(_id__in=ids)
        
        formset = FormSet(prefix=f'items{self.block.pk}', queryset=queryset,
                          block=self.block, instance=self.submission)
        return formset
    
    def post(self, request, *args, **kwargs):
        if 'block_id' not in self.request.POST:
            return HttpResponseBadRequest()
        
        self.block = get_object_or_404(CollectionBlock,
                                       form=self.program_form,
                                       pk=self.request.POST['block_id'])
        
        qs = self.submission._items.filter(_block=self.block.pk)
        nitems = qs.exclude(_file='', _filesize__gt=0).count()
        
        files, uploading = [], True
        for key, val in self.request.POST.items():
            if not key.startswith('filesize'): continue
            sizeval = key[len('filesize'):]
            size = None
            if sizeval.isdigit(): size = int(sizeval)
            if size is None: return HttpResponseBadRequest()
            files.append((val, size))

        if self.block.max_items and nitems >= self.block.max_items:
            if 'item_id' not in self.request.POST: return HttpResponse('')
        
        if 'item_id' in self.request.POST and len(files) != 1:
            return HttpResponseBadRequest()
        if not files:
            files.append((None, None))
            uploading = False
        
        items, ids = [], []
        for name, size in files:
            form = self.get_form(name=name, size=size)
            item = self.program_form.item_model(_submission=self.submission,
                                                _collection=self.block.name,
                                                _block=self.block.pk)
            if 'item_id' in self.request.POST:
                item = get_object_or_404(self.program_form.item_model,
                                         _submission=self.submission.pk,
                                         _id=self.request.POST['item_id'])
            else:
                nitems += 1
            
            if self.block.max_items and nitems > self.block.max_items: break
            if uploading and self.program_form.status == Form.Status.COMPLETED:
                if 'item_id' in self.request.POST:
                    ids.append(item._id)
                    items.append(item)
                break
            
            if not form.is_valid():
                item._error = True
                if form.has_error('name'):
                    msg = form.errors['name'][0]
                elif form.has_error('size'):
                    msg = form.errors['size'][0]
                else: msg = form.non_field_errors()[0]
                item._message = msg[:SubmissionItem._message_maxlen()]
            else:
                if item._file:
                    rec = SubmissionRecord.objects.get(
                        submission=self.submission.pk,
                        type=SubmissionRecord.RecordType.FILES
                    )
                    rec.number = F('number') - item._filesize
                    rec.save()
                    
                    item._file, item._filesize = '', 0
                    delete_file(item._file)
                
                if name:
                    if self.block.autoinit_filename():
                        setattr(item, self.block.name1, name[:name.rindex('.')])
                    item._file, item._filesize = '', size
                
                item._error, item._message = False, ''
            
            item.save()
            ids.append(item._id)
            items.append(item)
        
        c = self.get_context_data(items=items, uploading=uploading,
                                  formset=self.get_formset(ids),
                                  field_labels=self.program_form.field_labels())
        return self.render_to_response(c)


class SubmissionItemBase(SubmissionBase):
    def get_item(self, for_update=False):
        if 'item_id' not in self.request.POST: return HttpResponseBadRequest()
        
        if for_update:
            queryset = self.program_form.item_model.objects.select_for_update()
        else: queryset = self.program_form.item_model.objects.all()
        
        try:
            return queryset.get(_submission=self.submission.pk,
                                _id=self.request.POST['item_id'])
        except queryset.model.DoesNotExist:
            name = queryset.model._meta.object_name
            raise Http404(f'No {name} matches the given query.')


class SubmissionItemUploadView(SubmissionItemBase):
    http_method_names = ['post']
    
    def post(self, request, *args, **kwargs):
        item = self.get_item()
        
        block = get_object_or_404(CollectionBlock,
                                  form=self.program_form,
                                  pk=item._block)
        
        if 'file' not in self.request.FILES: return HttpResponseBadRequest()
        if item._error: return HttpResponseBadRequest()
        
        item._file = self.request.FILES['file']
        if item._file.size != item._filesize: return HttpResponseBadRequest()
        
        types = block.allowed_filetypes()
        
        item.save()
        path = item._file.path
        
        id_filename = os.path.join(os.path.dirname(path), 'id.txt')
        if not os.path.isfile(id_filename):
            with open(id_filename, 'w') as id_file:
                id_file.write(self.submission._email + '\n')
        
        filetype_class = FileType.by_extension(get_file_extension(path))
        # the extension was supposed to be already validated
        if not filetype_class and types: return HttpResponseBadRequest()
        
        msg_maxlen = SubmissionItem._message_maxlen()
        def item_error(item, msg):
            item._error, item._message = True, msg[:msg_maxlen]
            delete_file(item._file)
            item._file, item._filesize = '', 0
            return msg
        
        msg = ''
        if filetype_class:
            filetype = filetype_class()
            meta = filetype.meta(path)
            if 'error' in meta: msg = item_error(item, meta['error'])
            else:
                file_limits = block.file_limits()
                if filetype.TYPE in file_limits:
                    msg = filetype.limit_error(meta, file_limits[filetype.TYPE])
                    if msg: item_error(item, msg)
                    else: msg = ''
                
                if not item._error:
                    opts = block.process_options(filetype.TYPE)
                    newmeta = filetype.process(item._file, meta, **opts)
                    if 'error' in newmeta:
                        msg = item_error(item, newmeta['error'])
                    else:
                        if 'message' in newmeta:
                            warn_msg = newmeta.pop('message')
                            item._message = warn_msg[:msg_maxlen]
                        if 'update_filesize' in newmeta:
                            item._filesize = newmeta.pop('update_filesize')
                        item._filemeta = newmeta
            item.save()
            
        rec, created = SubmissionRecord.objects.get_or_create(
            program=self.program_form.program, form=self.program_form.slug,
            submission=self.submission.pk,
            type=SubmissionRecord.RecordType.FILES
        )
        if created: rec.number = item._filesize
        else: rec.number = F('number') + item._filesize
        rec.save()
        
        return HttpResponse(msg)


class SubmissionItemRemoveView(SubmissionItemBase):
    http_method_names = ['post']
    
    def post(self, request, *args, **kwargs):
        file = None
        with transaction.atomic():
            item = self.get_item(for_update=True)
            file, filesize = item._file, item._filesize
            item.delete()
        
        if file:
            rec = SubmissionRecord.objects.get(
                submission=self.submission.pk,
                type=SubmissionRecord.RecordType.FILES
            )
            rec.number = F('number') - filesize
            rec.save()
            
            delete_file(file)
        
        return HttpResponse('')


class SubmissionItemMoveView(SubmissionItemBase):
    http_method_names = ['post']
    
    def post(self, request, *args, **kwargs):
        if 'rank' not in self.request.POST: return HttpResponseBadRequest()
        rank = self.request.POST['rank']
        if not rank.isdigit() or int(rank) <= 0:
            return HttpResponseBadRequest()
        
        item = self.get_item()
        item._rank = int(rank)
        
        item.save()
        return HttpResponse('')
