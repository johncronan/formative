from django.urls import path

from . import views

urlpatterns = [
    path('', views.ProgramIndexView.as_view(), name='program_index'),
    path('<slug:slug>/', views.ProgramView.as_view(), name='program'),
    path('<slug:program_slug>/<slug:form_slug>/',
         views.ProgramFormView.as_view(), name='form'),
    path('<slug:program_slug>/<slug:form_slug>/continue',
             views.ProgramFormView.as_view(template_name='apply/continue.html'),
             name='form_continue'),
    path('<slug:program_slug>/<slug:form_slug>/<uuid:sid>/',
         views.SubmissionView.as_view(first_page=True), name='submission'),
    path('<slug:program_slug>/<slug:form_slug>/<uuid:sid>/page-<int:page>',
         views.SubmissionView.as_view(), name='submission_page'),
    path('<slug:program_slug>/<slug:form_slug>/<uuid:sid>/review',
         views.SubmissionView.as_view(template_name='apply/review.html'),
         name='submission_review'),
    path('<slug:program_slug>/<slug:form_slug>/<uuid:sid>/item',
         views.SubmissionItemView.as_view(), name='item'),
    path('<slug:program_slug>/<slug:form_slug>/<uuid:sid>/file',
         views.SubmissionItemView.as_view(upload=True), name='item_file'),
    path('<slug:program_slug>/<slug:form_slug>/<uuid:sid>/removeitem',
         views.SubmissionItemRemoveView.as_view(), name='item_remove'),
    path('<slug:program_slug>/<slug:form_slug>/<uuid:sid>/moveitem',
         views.SubmissionItemMoveView.as_view(), name='item_move'),
]
