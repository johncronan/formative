from django.urls import include, path
from django.views.defaults import page_not_found, server_error
from django.http import Http404

from formative import admin


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('formative.urls')),
#    path('404/', page_not_found, {'exception': Http404()}),
#    path('500/', server_error),
]
