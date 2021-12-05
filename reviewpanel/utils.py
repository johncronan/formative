from django.apps import apps
from django.apps.config import AppConfig
from django.db import models
from django.contrib import admin


def create_model(name, fields, app_label='reviewpanel', module='',
                 table_prefix=None, meta=None, base_class=models.Model):
    class Meta:
        pass

    setattr(Meta, 'app_label', app_label)
    if meta is not None:
        for key, value in meta.__dict__.items():
            if key[:2] == '__' or key == 'abstract': continue
            setattr(Meta, key, value)
    if table_prefix: setattr(Meta, 'db_table', f'{table_prefix}_{name}')
    
    if not module: module = app_label
    attrs = {'__module__': module, 'Meta': Meta}
    attrs.update(dict(fields)) # TODO: how do I keep the order

    # Create the class, which automatically triggers ModelBase processing
    model = type(name, (base_class,), attrs)
    return model
