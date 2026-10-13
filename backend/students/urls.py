from django.urls import path

from . import views

urlpatterns = [
    path("", views.StudentListCreateView.as_view(), name="student-list"),
    path("me/", views.StudentMeView.as_view(), name="student-me"),
    path("me/counsellor/", views.StudentCounsellorView.as_view(), name="student-me-counsellor"),
    path("<str:student_id>/", views.StudentDetailView.as_view(), name="student-detail"),
    path("<str:student_id>/assign-counsellor/", views.AssignCounsellorView.as_view(), name="student-assign"),
]
