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


class FormView(generic.DetailView):
    model = Form
    template_name = 'apply/form.html'
    
    def get_object(self):
        return get_object_or_404(Form,
                                 program__slug=self.kwargs['program_slug'],
                                 slug=self.kwargs['form_slug'])


class SubmissionCreateView(generic.CreateView):
    fields = ['_email']
    
    def get_queryset(self):
        form = get_object_or_404(Form,
                                 program__slug=self.kwargs['program_slug'],
                                 slug=self.kwargs['form_slug'])
        if not form.model: raise Http404
        
        return form.model.objects.all()
