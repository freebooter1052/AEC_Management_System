from django.urls import include, path

from core.views import HealthView

urlpatterns = [
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/auth/", include("authentication.urls")),
    path("api/students/", include("students.urls")),
    path("api/counsellors/", include("counsellors.urls")),
    path("api/", include("master_data.urls")),
    path("", include("frontend.urls")),
]
