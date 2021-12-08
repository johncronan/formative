from django import template

register = template.Library()

@register.inclusion_tag('apply/program_forms.html')
def show_program(program):
    return { 'program': program }
