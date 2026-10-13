from django.urls import path

from . import views

urlpatterns = [
    path("", views.CounsellorListCreateView.as_view(), name="counsellor-list"),
    path("options/", views.CounsellorOptionsView.as_view(), name="counsellor-options"),
    path("me/", views.CounsellorMeView.as_view(), name="counsellor-me"),
    path("<str:counsellor_id>/", views.CounsellorDetailView.as_view(), name="counsellor-detail"),
    path("<str:counsellor_id>/students/", views.CounsellorStudentsView.as_view(), name="counsellor-students"),
]
