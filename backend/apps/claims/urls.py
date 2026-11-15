from django.urls import path

from . import lawyer_views, views

urlpatterns = [
    path("cases/<uuid:case_id>/claim", views.ClaimView.as_view()),
    path("cases/<uuid:case_id>/claim/personal-data", views.PersonalDataView.as_view()),
    path("cases/<uuid:case_id>/claim/submit", views.SubmitView.as_view()),
    path("cases/<uuid:case_id>/claim/accept-edits", views.AcceptEdits.as_view()),
    path("cases/<uuid:case_id>/claim/reject-edits", views.RejectEdits.as_view()),
    path("cases/<uuid:case_id>/claim/mark-sent", views.MarkSent.as_view()),
    path("cases/<uuid:case_id>/claim/outcome", views.Outcome.as_view()),
    path("lawyer/claims", lawyer_views.Queue.as_view()),
    path("lawyer/claims/<uuid:claim_id>", lawyer_views.ReviewDetail.as_view()),
    path("lawyer/claims/<uuid:claim_id>/take", lawyer_views.Take.as_view()),
    path("lawyer/claims/<uuid:claim_id>/approve", lawyer_views.Approve.as_view()),
    path("lawyer/claims/<uuid:claim_id>/edit", lawyer_views.Edit.as_view()),
]
