from django.urls import path

from . import views

urlpatterns = [
    path('', views.ProgramIndexView.as_view(), name='program_index'),
    path('<slug:slug>/', views.ProgramView.as_view(), name='program'),
    path('<slug:program_slug>/<slug:form_slug>/', views.FormView.as_view(),
         name='form')
]
