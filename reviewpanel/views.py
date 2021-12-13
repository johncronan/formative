from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from .models import Program, Form


class ProgramIndexView(generic.ListView):
    template_name = 'apply/index.html'
    context_object_name = 'programs'
    
    def get_queryset(self):
        return Program.objects.filter(hidden=False)


class ProgramView(generic.DetailView):
    model = Program
    template_name = 'apply/program.html'
    slug_field = 'slug'


class DynamicFormView:
    def get_program_form(self):
        return get_object_or_404(Form,
                                 program__slug=self.kwargs['program_slug'],
                                 slug=self.kwargs['form_slug'])

    
class FormView(generic.CreateView, DynamicFormView):
    template_name = 'apply/form.html'
    fields = ['_email']
    
    def get_queryset(self):
        self.program_form = self.get_program_form()
        if not self.program_form.model: raise Http404
        
        return self.program_form.model.objects.all()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['program_form'] = self.program_form
        return context
    
    def get_success_url(self):
        return reverse('submission', kwargs={
            'program_slug': self.program_form.program.slug,
            'form_slug': self.program_form.slug,
            'sid': self.object._id
        })


class SubmissionView(generic.UpdateView, DynamicFormView):
    template_name = 'apply/submission.html'
    fields = ['_email']
    context_object_name = 'submission'
    
    def get_object(self):
        form = self.get_program_form()
        if not form.model: raise Http404
        
        submission = get_object_or_404(form.model, _id=self.kwargs['sid'])
        return submission
