from django.urls import path

from . import views

urlpatterns = [
    path("", views.RecommendationListView.as_view(), name="recommendation-list"),
    path("generate/", views.RecommendationGenerateView.as_view(), name="recommendation-generate"),
    path("<str:recommendation_id>/", views.RecommendationDetailView.as_view(), name="recommendation-detail"),
]
