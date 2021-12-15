from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.forms.models import modelform_factory
from django.views import generic

from .models import Program, Form
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


class DynamicFormMixin:
    def get_program_form(self):
        return get_object_or_404(Form,
                                 program__slug=self.kwargs['program_slug'],
                                 slug=self.kwargs['form_slug'])


class ProgramFormView(generic.edit.ProcessFormView,
                      generic.detail.SingleObjectTemplateResponseMixin,
                      generic.edit.FormMixin, DynamicFormMixin):
    template_name = 'apply/form.html'
    form_class = OpenForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        program_form = self.get_program_form()
        if not program_form.model: raise Http404
        
        context['program_form'] = program_form
        return context
    
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
    
    def get_form(self):
        form = self.get_program_form()
        if not form.model: raise Http404
        
        form = modelform_factory(form.model, form=SubmissionForm,
                                 exclude=['_created', '_modified',
                                          '_submitted', '_email'])
        return form
    
    def get_object(self):
        form = self.get_program_form()
        if not form.model: raise Http404
        
        submission = get_object_or_404(form.model, _id=self.kwargs['sid'])
        return submission
