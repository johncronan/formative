from django.db import models
from django.contrib import admin


def create_model(name, fields, app_label='reviewpanel', module='',
                 options=None, admin_opts=None):
    class Meta:
        pass

    setattr(Meta, 'app_label', app_label)
    if options is not None:
        for key, value in options.items():
            if key[:2] == '__': continue
            setattr(Meta, key, value)

    attrs = {'__module__': module, 'Meta': Meta}
    attrs.update(fields)

    # Create the class, which automatically triggers ModelBase processing
    model = type(name, (models.Model,), attrs)

    if admin_opts is not None:
        class Admin(admin.ModelAdmin):
            pass
        for key, value in admin_opts:
            setattr(Admin, key, value)
        admin.site.register(model, Admin)

    return model
