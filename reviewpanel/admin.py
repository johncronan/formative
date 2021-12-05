from django.contrib import admin
from polymorphic.admin import (PolymorphicParentModelAdmin,
                               PolymorphicChildModelAdmin,
                               PolymorphicChildModelFilter)

from .models import Program, Form, FormLabel, FormBlock, FormDependency, \
    CustomBlock, CollectionBlock

admin.site.register(Program)

admin.site.register(Form)

admin.site.register(FormLabel)

admin.site.register(FormDependency)

@admin.register(FormBlock)
class FormBlockAdmin(PolymorphicParentModelAdmin):
    child_models = (FormBlock, CustomBlock, CollectionBlock)
    list_filter = (PolymorphicChildModelFilter,)

@admin.register(CustomBlock)
class CustomBlockAdmin(PolymorphicChildModelAdmin):
    base_model = FormBlock

@admin.register(CollectionBlock)
class CollectionBlockAdmin(PolymorphicChildModelAdmin):
    base_model = FormBlock
