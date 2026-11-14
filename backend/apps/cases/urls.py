from django.urls import path

from . import views

urlpatterns = [
    path("cases", views.Cases.as_view()),
    path("cases/<uuid:case_id>", views.CaseDetail.as_view()),
    path("cases/<uuid:case_id>/messages", views.Messages.as_view()),
    path("cases/<uuid:case_id>/documents", views.Documents.as_view()),
    path("cases/<uuid:case_id>/documents/<uuid:document_id>/content", views.Download.as_view()),
    path("cases/<uuid:case_id>/close", views.CloseCase.as_view()),
]
