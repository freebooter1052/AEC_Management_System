from django.urls import path

from . import views

urlpatterns = [
    path("", views.UniversityListView.as_view(), name="university-list"),
    path("countries/", views.UniversityCountriesView.as_view(), name="university-countries"),
    path("courses/", views.CourseListView.as_view(), name="course-list"),
    path("<str:university_id>/", views.UniversityDetailView.as_view(), name="university-detail"),
]
