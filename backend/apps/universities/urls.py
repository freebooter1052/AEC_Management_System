from django.urls import path

from . import views

urlpatterns = [
    path("", views.UniversityListView.as_view(), name="university-list"),
    path("countries/", views.UniversityCountriesView.as_view(), name="university-countries"),
    path("courses/", views.CourseListView.as_view(), name="course-list"),
    path("courses/<str:course_id>/", views.CourseDetailView.as_view(), name="course-detail"),
    path("<str:university_id>/", views.UniversityDetailView.as_view(), name="university-detail"),
    path("<str:university_id>/courses/", views.UniversityCourseCreateView.as_view(), name="university-course-create"),
]
