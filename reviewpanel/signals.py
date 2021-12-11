from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Form, FormBlock
from .stock import EmailWidget


@receiver(post_save, sender=Form)
def form_post_save(sender, instance, created, **kwargs):
    if not created: return
    
    form = instance
    if form.validation_type == Form.Validation.EMAIL:
        b = FormBlock(form=form, page=0, rank=0, name='email',
                      options=EmailWidget.default_options())
        b.save()
