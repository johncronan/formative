from django.db import models
from django.core.exceptions import ValidationError
from django.utils.text import slugify


class AutoSlugModel(models.Model):
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        if self._state.adding:
            self.db_slug = self.slug.replace('-', '')
        try:
            super().save(*args, **kwargs)
        except ValidationError as e:
            raise ValidationError(_('Name must be unique (with non-' +
                                  'alphanumeric characters removed)')) from e
