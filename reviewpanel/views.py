from django.http import HttpResponse, HttpResponseRedirect, Http404, \
    HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django import forms
from django.db.models import Min
from django.forms.models import modelform_factory
from django.views import generic
import itertools

from .models import Program, Form, FormBlock, CustomBlock, CollectionBlock
from .forms import OpenForm, SubmissionForm, SubmissionItemForm


class ProgramIndexView(generic.ListView):
    template_name = 'apply/index.html'
    context_object_name = 'programs'
    
    def get_queryset(self):
        return Program.objects.filter(hidden=False)


class ProgramView(generic.DetailView):
    model = Program
    template_name = 'apply/program.html'
    slug_field = 'slug'


class ProgramFormMixin(generic.edit.FormMixin):
    def dispatch(self, request, *args, **kwargs):
        form = get_object_or_404(Form,
                                 program__slug=self.kwargs['program_slug'],
                                 slug=self.kwargs['form_slug'])
        self.program_form = form

        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not self.program_form.model: raise Http404
        
        context['program_form'] = self.program_form
        return context


class ProgramFormView(ProgramFormMixin, generic.edit.ProcessFormView,
                      generic.base.TemplateResponseMixin):
    template_name = 'apply/form.html'
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

        self.object._send_email(form=self.program_form,
                                template='continue.html')
        return super().form_valid(form)


class SubmissionView(ProgramFormMixin, generic.UpdateView):
    template_name = 'apply/submission.html'
    context_object_name = 'submission'
    first_page = False
    
    def dispatch(self, request, *args, **kwargs):
        self.page = None
        if 'page' in self.kwargs: self.page = self.kwargs['page']
        if self.first_page: self.page = 1

        self.skipped, self.blocks_by_name = {}, {}
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_object(self):
        submission = get_object_or_404(self.program_form.model,
                                       _id=self.kwargs['sid'])
        return submission

    def get_form(self):
        fields, widgets, customs, stocks = [], {}, {}, {}

        query = self.program_form.blocks.all()
        if self.page: query = query.filter(page=self.page)
        elif self.request.method == 'POST': query = query.none()

        blocks_checked, enabled = {}, []
        skipped_pages = self.object._skipped[:self.page or self.object._valid]
        skipped_ids = dict.fromkeys(itertools.chain(*skipped_pages), True)
        
        for block in query:
            d_id = block.dependence_id
            if d_id and d_id not in blocks_checked:
                # when we encounter a new block that some field is dependent on,
                # if it isn't among the blocks that were already _skipped,
                # enable this page's fields with a dependency matching the value
                if d_id not in skipped_ids:
                     b = FormBlock.objects.get(id=d_id)
                     if b.block_type() == 'stock':
                         values = { n: getattr(self.object, n)
                                    for n in b.stock.field_names() }
                         v = b.stock.conditional_value(**values)
                     elif b.block_type() == 'custom':
                         v = b.conditional_value(getattr(self.object, b.name))
                     
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
                       **self.get_form_kwargs())
        return f
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context['program_form']
        
        context['field_labels'] = form.field_labels()
        if self.page:
            args, items = {'page': self.page, 'skip': self.skipped.keys()}, {}
            for item in form.visible_items(**args):
                if item._block not in items: items[item._block] = []
                items[item._block].append(item)
            
            context.update({
                'page': self.page,
                'prev_page': self.page > 1 and self.page - 1 or None,
                'visible_blocks': form.visible_blocks(**args),
                'visible_items': items
            })
        else: context['prev_page'] = form.num_pages()
        
        return context
    
    def reset_skipped(self, ids=None):
        # when resetting the results of later pages that have been invalidated,
        # we haven't yet encountered these blocks, so we have to look them up:
        if ids: skipped = self.program_form.blocks.filter(id__in=ids)
        else: skipped = self.skipped.values()
        
        for block in skipped:
            for name, f in block.fields():
                setattr(self.object, name, None)
    
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
            # the draft submission will now be marked as submitted
            self.object._submit()
            
            return HttpResponseRedirect(reverse('thanks',
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
        self.object._skipped[self.page-1] = list(self.skipped.keys())
        self.reset_skipped()
        
        self.object.save()
        return HttpResponseRedirect(self.get_success_url())

    def url_args(self, id=True):
        args = {
            'program_slug': self.program_form.program.slug,
            'form_slug': self.program_form.slug
        }
        if id: args['sid'] = self.object._id
        return args
        
    def render_to_response(self, context):
        if self.object._submitted:
            return HttpResponseRedirect(reverse('thanks',
                                                kwargs=self.url_args(id=False)))
        
        if (self.page and context['page'] <= self.object._valid + 1
         or self.object._valid == self.program_form.num_pages()):
            return super().render_to_response(context)

        # tried to skip ahead - go back to the last page that can be displayed
        p, name, args = self.object._valid, 'submission_page', self.url_args()
        if p: args['page'] = p + 1
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


class SubmissionItemView(ProgramFormMixin, generic.View,
                         generic.base.TemplateResponseMixin):
    template_name = 'apply/collection_items_new.html'
    http_method_names = ['post']
    upload = False
    
    def get_form(self, file):
        if not self.block.has_file: return forms.Form()
        return SubmissionItemForm(block=self.block, files={'file': file})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(form=None, **kwargs)
        
        context['form_block'] = self.block
        
        return context
    
    def post(self, request, *args, **kwargs):
        if not self.program_form.item_model: raise Http404
        
        self.submission = get_object_or_404(self.program_form.model,
                                            _id=self.kwargs['sid'])
        
        if not self.upload:
            if 'block_id' not in self.request.POST:
                return HttpResponseBadRequest()
            
            self.block = get_object_or_404(CollectionBlock,
                                           form=self.program_form,
                                           pk=self.request.POST['block_id'])
            items = []
            for val in self.request.FILES.getlist('file'):
                form = self.get_form(val)
                item = self.program_form.item_model(_submission=self.submission,
                                                    _collection=self.block.name,
                                                    _block=self.block.pk)
                if not form.is_valid():
                    item._error = True
                    msg = form.errors['file'] and form.errors['file'][0] or ''
                    item._message = msg
                item.save()
                items.append(item)
            
            return  self.render_to_response(self.get_context_data(items=items))
