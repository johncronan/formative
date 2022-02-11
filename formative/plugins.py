from django.apps import AppConfig, apps
from django.core.exceptions import ImproperlyConfigured

import sys


def get_all_plugins(form=None):
    plugins = []
    for app in apps.get_app_configs():
        if hasattr(app, 'FormativePluginMeta'):
            meta = app.FormativePluginMeta
            meta.module, meta.app = app.name, app
            
            if hasattr(app, 'is_available') and form:
                if not app.is_available(form): continue
            
            plugins.append(meta)
    
    return plugins

def get_matching_plugin(module):
    for app in apps.get_app_configs():
        if hasattr(app, 'FormativePluginMeta'):
            if app.name == module or module.startswith(app.name + '.'):
                meta = app.FormativePluginMeta
                meta.module, meta.app = app.name, app
                
                return meta
    return None


class PluginConfig(AppConfig):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not hasattr(self, 'FormativePluginMeta'):
            msg = 'Formative plugin config needs a FormativePluginMeta class.'
            raise ImproperlyConfigured(msg)
        
        if hasattr(self.FormativePluginMeta, 'compatibility'):
            import pkg_resources
            try:
                pkg_resources.require(self.FormativePluginMeta.compatibility)
            except pkg_resources.VersionConflict as e:
                print('Incompatible plugins found.')
                print(f'Plugin {self.name} requires {e.req}, '
                      f'but you installed {e.dist}.')
                sys.exit(1)
