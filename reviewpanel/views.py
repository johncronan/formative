from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic

from .models import Program, Form


class ProgramIndexView(generic.ListView):
    template_name = 'apply/index.html'
    context_object_name = 'programs'
    
    def get_queryset(self):
        return Program.objects.all()


class ProgramView(generic.DetailView):
    model = Program
    template_name = 'apply/program.html'
    slug_field = 'slug'
