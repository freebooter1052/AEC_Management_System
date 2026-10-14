from django.urls import path

from . import views

urlpatterns = [
    path("", views.IntakeListCreateView.as_view(), name="intake-list"),
    path("<str:intake_id>/", views.IntakeDetailView.as_view(), name="intake-detail"),
]
