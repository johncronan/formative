from django.urls import path

from . import views

urlpatterns = [
    path('', views.ProgramIndexView.as_view(), name='program_index'),
    path('<slug:slug>/', views.ProgramView.as_view(), name='program'),
    path('<slug:program_slug>/<slug:form_slug>/',
         views.ProgramFormView.as_view(), name='form'),
    path('<slug:program_slug>/<slug:form_slug>/<uuid:sid>/',
         views.SubmissionView.as_view(), name='submission')
]
