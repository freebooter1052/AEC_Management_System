"""
Root URL map.

    /api/...  REST API (one include per domain app)
    /...      web pages from the top-level `frontend/` folder. Each page is a static
              shell that loads its data from the API with the user's bearer token;
              every permission is enforced by the API, not by these routes.
"""

from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from apps.core.views import HealthView


def page(name: str):
    return TemplateView.as_view(template_name=f"pages/{name}.html")


api_patterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.accounts.urls")),
    path("students/", include("apps.students.urls")),
    path("counsellors/", include("apps.counsellors.urls")),
    path("universities/", include("apps.universities.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
]

page_patterns = [
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("login/", page("login"), name="login"),
    path("register/", page("register"), name="register"),
    path("dashboard/", page("dashboard"), name="dashboard-page"),
    path("profile/", page("profile"), name="profile"),
    path("students/", page("students"), name="students"),
    path("students/<str:student_id>/", page("profile"), name="student-profile"),
    path("counsellors/", page("counsellors"), name="counsellors"),
    path("universities/", page("universities"), name="universities"),
]

urlpatterns = [
    path("api/", include(api_patterns)),
    *page_patterns,
]
