from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django import forms
from django.forms.models import modelform_factory
from django.views import generic
import itertools

from .models import Program, Form, FormBlock, CustomBlock
from .forms import OpenForm, SubmissionForm


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
                      generic.detail.SingleObjectTemplateResponseMixin):
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

        self.skipped = {}
        
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
                
                if block.block_type() == 'custom':
                    customs[name] = block
                    if block.type == CustomBlock.InputType.CHOICE:
                        widgets[name] = forms.RadioSelect
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
            context.update({
                'page': self.page,
                'prev_page': self.page > 1 and self.page - 1 or None,
                'visible_blocks': form.visible_blocks(page=self.page,
                                                      skip=self.skipped.keys())
            })
        else: context['prev_page'] = form.num_pages()
        
        return context
    
    def reset_skipped(self):
        for block in self.skipped.values():
            for name, f in block.fields():
                nullval = ''
                if block.block_type() == 'custom':
                    if block.type in (CustomBlock.InputType.NUMERIC,
                                      CustomBlock.InputType.BOOLEAN):
                        nullval = None
                else:
                    widget = None
                    if len(block.stock.widget_names()) > 1:
                        widget = name[1:][len(block.stock.name)+1:]
                    nullval = block.stock.null_value(widget=widget)
                
                setattr(self.object, name, nullval)
    
    def form_valid(self, form):
        if not self.page:
            # the draft submission will now be marked as submitted
            self.object._submit()
            
            return HttpResponseRedirect(reverse('thanks',
                                                kwargs=self.url_args(id=False)))
        
        self.object = form.save(commit=False)
        if self.object._valid < self.page: self.object._valid = self.page
        # TODO: if page < valid: special behavior
        # _valid = min(dependent blocks' page #, for changed blocks, if any) - 1
        # form.changed_data => turn into ids list => aggregate query
        
        self.object._skipped = self.object._skipped[:self.object._valid-1]
        self.object._skipped.append(list(self.skipped.keys()))
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
