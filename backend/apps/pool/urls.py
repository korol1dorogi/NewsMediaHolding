from django.urls import path

from . import views

urlpatterns = [
    path("cases/<uuid:case_id>/pool", views.Publish.as_view()),
    path("cases/<uuid:case_id>/offers", views.Offers.as_view()),
    path("cases/<uuid:case_id>/offers/<uuid:offer_id>/accept", views.AcceptOffer.as_view()),
    path("cases/<uuid:case_id>/work/accept", views.AcceptWork.as_view()),
    path("lawyer/pool", views.Pool.as_view()),
    path("lawyer/pool/<uuid:card_id>", views.PoolDetail.as_view()),
    path("lawyer/pool/<uuid:card_id>/offers", views.MakeOffer.as_view()),
    path("lawyer/cases", views.LawyerCases.as_view()),
    path("lawyer/cases/<uuid:case_id>", views.LawyerCaseDetail.as_view()),
    path("lawyer/cases/<uuid:case_id>/start", views.Start.as_view()),
    path("lawyer/cases/<uuid:case_id>/submit-work", views.SubmitWork.as_view()),
]
