from django.contrib import admin

from .models import Program, Form, FormLabel, FormBlock, FormDependency, \
    CustomBlock, CollectionBlock

admin.site.register(Program)

admin.site.register(Form)

admin.site.register(FormLabel)

admin.site.register(FormBlock)

admin.site.register(FormDependency)

