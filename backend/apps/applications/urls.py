from django.urls import path

from . import views

urlpatterns = [
    path("", views.ApplicationListCreateView.as_view(), name="application-list"),
    path("summary/", views.ApplicationSummaryView.as_view(), name="application-summary"),
    path("<str:application_id>/", views.ApplicationDetailView.as_view(), name="application-detail"),
    path("<str:application_id>/status/", views.ApplicationStatusView.as_view(), name="application-status"),
    path("<str:application_id>/history/", views.ApplicationHistoryView.as_view(), name="application-history"),
]
