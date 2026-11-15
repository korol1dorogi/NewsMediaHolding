from django.urls import path

from . import views

urlpatterns = [
    path("cases/<uuid:case_id>/claim", views.ClaimView.as_view()),
    path("cases/<uuid:case_id>/claim/personal-data", views.PersonalDataView.as_view()),
    path("cases/<uuid:case_id>/claim/submit", views.SubmitView.as_view()),
]
