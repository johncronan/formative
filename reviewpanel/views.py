from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django import forms
from django.forms.models import modelform_factory
from django.views import generic

from .models import Program, Form, CustomBlock
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


class DynamicFormMixin(generic.edit.FormMixin):
    def get_program_form(self):
        return get_object_or_404(Form,
                                 program__slug=self.kwargs['program_slug'],
                                 slug=self.kwargs['form_slug'])
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        program_form = self.get_program_form()
        if not program_form.model: raise Http404
        
        context['program_form'] = program_form
        return context


class ProgramFormView(generic.edit.ProcessFormView,
                      generic.detail.SingleObjectTemplateResponseMixin,
                      DynamicFormMixin):
    template_name = 'apply/form.html'
    form_class = OpenForm
    
    def get_success_url(self):
        program_form = self.get_program_form()
        
        return reverse('submission', kwargs={
            'program_slug': program_form.program.slug,
            'form_slug': program_form.slug,
            'sid': self.object._id
        })
    
    def form_valid(self, form):
        model = self.get_program_form().model
        self.object, created = model.objects.get_or_create(
            _email=form.cleaned_data['email']
        )
        # TODO: send the email
        return super().form_valid(form)


class SubmissionView(generic.UpdateView, DynamicFormMixin):
    template_name = 'apply/submission.html'
    context_object_name = 'submission'
    
    def dispatch(self, request, *args, **kwargs):
        page = 1
        if 'page' in self.kwargs: page = int(self.kwargs['page'])
        self.page = page
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form(self):
        form = self.get_program_form()
        if not form.model: raise Http404

        fields, widgets, radios = [], {}, []
        for block in form.blocks.filter(page=self.page):
            for name, field in block.fields():
                fields.append(name)
                if type(block) == CustomBlock:
                    if block.type == CustomBlock.InputType.CHOICE:
                        widgets[name] = forms.RadioSelect
                        radios.append(name)
            
        form_class = modelform_factory(form.model, form=SubmissionForm,
                                       fields=fields, widgets=widgets,
                                       exclude=['_created', '_modified',
                                                '_submitted', '_email'])
        
        f = form_class(**self.get_form_kwargs())
        for n in radios:
            # TODO: use formfield_callback instead, to specify empty_label=None
            f.fields[n].choices = f.fields[n].choices[1:]

        return f
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context['program_form']
        
        context['page'] = self.page
        context['visible_blocks'] = form.visible_blocks(page=self.page)
        context['field_labels' ] = form.field_labels()
        
        return context
        
    def get_object(self):
        form = self.get_program_form()
        if not form.model: raise Http404
        
        submission = get_object_or_404(form.model, _id=self.kwargs['sid'])
        return submission
    
    def get_success_url(self):
        form = self.get_program_form()
        
        kwargs = {
            'program_slug': form.program.slug,
            'form_slug': form.slug,
            'sid': self.object._id,
        }
        
        if self.page == form.num_pages(): name = 'submission_review'
        else:
            kwargs['page'] = self.page + 1
            name = 'submission_page'
        
        return reverse(name, kwargs=kwargs)
