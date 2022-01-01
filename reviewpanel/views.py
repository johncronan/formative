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
    first_page = False
    
    def dispatch(self, request, *args, **kwargs):
        self.page = None
        if 'page' in self.kwargs: self.page = self.kwargs['page']
        if self.first_page: self.page = 1
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form(self):
        fields, widgets, radios = [], {}, []

        if self.page:
            for block in self.program_form.blocks.filter(page=self.page):
                for name, field in block.fields():
                    fields.append(name)
                    
                    if block.block_type() == 'custom':
                        if block.type == CustomBlock.InputType.CHOICE:
                            widgets[name] = forms.RadioSelect
                            radios.append(name)
            
        form_class = modelform_factory(self.program_form.model,
                                       form=SubmissionForm,
                                       fields=fields, widgets=widgets)
        
        f = form_class(**self.get_form_kwargs())
        for n in radios:
            # TODO: use formfield_callback instead, to specify empty_label=None
            f.fields[n].choices = f.fields[n].choices[1:]

        return f
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context['program_form']
        
        if self.page:
            context.update({
                'page': self.page,
                'prev_page': self.page > 1 and self.page - 1 or None,
                'visible_blocks': form.visible_blocks(page=self.page),
                'field_labels': form.field_labels(),
            })
        else: context['prev_page'] = form.num_pages()
        
        return context
    
    def get_object(self):
        submission = get_object_or_404(self.program_form.model,
                                       _id=self.kwargs['sid'])
        return submission

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
    
    def form_valid(self, form):
        if not self.page:
            # the draft submission will now be marked as submitted
            self.object._submit()
            
            return HttpResponseRedirect(reverse('thanks',
                                                kwargs=self.url_args(id=False)))
        
        self.object = form.save(commit=False)
        # TODO: state inconsistency possible if _valid > page - on later pages 
        # we need to clear, ensure it happens for the blocks that we later skip
        self.object._valid = self.page
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

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
