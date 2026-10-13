from django.urls import path

from core.views import DashboardView

from . import views

urlpatterns = [
    path("universities/", views.UniversityListView.as_view(), name="university-list"),
    path("universities/countries/", views.UniversityCountriesView.as_view(), name="university-countries"),
    path("universities/<str:university_id>/", views.UniversityDetailView.as_view(), name="university-detail"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
