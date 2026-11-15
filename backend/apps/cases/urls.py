from django.urls import path

from . import card_views, path_views, views

urlpatterns = [
    path("cases", views.Cases.as_view()),
    path("cases/<uuid:case_id>", views.CaseDetail.as_view()),
    path("cases/<uuid:case_id>/messages", views.Messages.as_view()),
    path("cases/<uuid:case_id>/documents", views.Documents.as_view()),
    path("cases/<uuid:case_id>/documents/<uuid:document_id>/content", views.Download.as_view()),
    path("cases/<uuid:case_id>/close", views.CloseCase.as_view()),
    path("cases/<uuid:case_id>/card", card_views.Card.as_view()),
    path("cases/<uuid:case_id>/card/facts/<str:key>", card_views.EditFact.as_view()),
    path("cases/<uuid:case_id>/card/confirm", card_views.Confirm.as_view()),
    path("cases/<uuid:case_id>/company", path_views.Company.as_view()),
    path("cases/<uuid:case_id>/paths", path_views.Paths.as_view()),
    path("cases/<uuid:case_id>/path", path_views.ChoosePath.as_view()),
    path("cases/<uuid:case_id>/plan", path_views.Plan.as_view()),
]
