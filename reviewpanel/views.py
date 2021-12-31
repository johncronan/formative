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
    
    def get_success_url(self):
        return reverse('submission', kwargs={
            'program_slug': self.program_form.program.slug,
            'form_slug': self.program_form.slug,
            'sid': self.object._id
        })
    
    def form_valid(self, form):
        model = self.program_form.model
        self.object, created = model.objects.get_or_create(
            _email=form.cleaned_data['email']
        )
        # TODO: send the email
        return super().form_valid(form)


class SubmissionView(ProgramFormMixin, generic.UpdateView):
    template_name = 'apply/submission.html'
    context_object_name = 'submission'
    
    def dispatch(self, request, *args, **kwargs):
        page = 1
        if 'page' in self.kwargs: page = int(self.kwargs['page'])
        self.page = page
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form(self):
        fields, widgets, radios = [], {}, []
        
        for block in self.program_form.blocks.filter(page=self.page):
            for name, field in block.fields():
                fields.append(name)
                
                if block.block_type() == 'custom':
                    if block.type == CustomBlock.InputType.CHOICE:
                        widgets[name] = forms.RadioSelect
                        radios.append(name)
            
        form_class = modelform_factory(self.program_form.model,
                                       form=SubmissionForm,
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
        
        context.update({
            'page': self.page,
            'prev_page': self.page > 1 and self.page - 1 or None,
            'visible_blocks': form.visible_blocks(page=self.page),
            'field_labels': form.field_labels(),
        })
        return context
        
    def get_object(self):
        submission = get_object_or_404(self.program_form.model,
                                       _id=self.kwargs['sid'])
        return submission
    
    def get_success_url(self):
        kwargs = {
            'program_slug': self.program_form.program.slug,
            'form_slug': self.program_form.slug,
            'sid': self.object._id,
        }

        name = 'submission_page'
        if 'continue' in self.request.POST:
            if self.page == self.program_form.num_pages(): # we're done
                name = 'submission_review'
            else: kwargs['page'] = self.page + 1
        else:
            if self.page == 1: name = 'submission'
            else: kwargs['page'] = self.page
        
        return reverse(name, kwargs=kwargs)
