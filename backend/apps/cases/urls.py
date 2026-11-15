from django.urls import path

from . import card_views, views

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
]
