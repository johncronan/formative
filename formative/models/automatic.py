from django.db import models
from django.core.exceptions import ValidationError
from django.utils.text import slugify


class AutoSlugModel(models.Model):
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        self.db_slug = self.slug.lower().replace('-', '')
        
        try:
            super().save(*args, **kwargs)
        except ValidationError as e:
            msg = _('Name (with hyphens removed) must be unique.')
            raise ValidationError(msg) from e
