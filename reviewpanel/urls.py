from django.urls import path

from . import views

urlpatterns = [
    path('', views.ProgramIndexView.as_view(), name='program_index'),
    path('program/<int:pk>/', views.ProgramView.as_view(), name='program'),
]
