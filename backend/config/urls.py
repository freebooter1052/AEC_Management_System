"""
Root URL map.

    /api/...  REST API (one include per domain app)
    /...      the React app built from the top-level `frontend/` folder. Every page URL
              returns the same index.html and React Router renders the page; data is loaded
              from the API with the user's bearer token, and every permission is enforced
              by the API, not by these routes.
"""

from django.urls import include, path, re_path
from django.views.generic import RedirectView

from apps.core.views import HealthView, frontend_app, frontend_not_found
from apps.universities.views import CountryListView


api_patterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("countries/", CountryListView.as_view(), name="countries"),
    path("auth/", include("apps.accounts.urls")),
    path("students/", include("apps.students.urls")),
    path("counsellors/", include("apps.counsellors.urls")),
    path("universities/", include("apps.universities.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("applications/", include("apps.applications.urls")),
    path("intakes/", include("apps.applications.intake_urls")),
    path("documents/", include("apps.documents.urls")),
    path("counselling/", include("apps.counselling.urls")),
    path("recommendations/", include("apps.recommendations.urls")),
    path("notifications/", include("apps.notifications.urls")),
]

page_patterns = [
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("login/", frontend_app, name="login"),
    path("register/", frontend_app, name="register"),
    path("forgot-password/", frontend_app, name="forgot-password"),
    path("dashboard/", frontend_app, name="dashboard-page"),
    path("profile/", frontend_app, name="profile"),
    path("students/", frontend_app, name="students"),
    path("students/<str:student_id>/", frontend_app, name="student-profile"),
    path("counsellors/", frontend_app, name="counsellors"),
    path("universities/", frontend_app, name="universities"),
    path("applications/", frontend_app, name="applications"),
    path("applications/<str:application_id>/", frontend_app, name="application-page"),
    path("documents/", frontend_app, name="documents"),
    path("counselling/", frontend_app, name="counselling"),
    path("recommendations/", frontend_app, name="recommendations-page"),
    path("notifications/", frontend_app, name="notifications-page"),
]

urlpatterns = [
    path("api/", include(api_patterns)),
    path("favicon.ico", RedirectView.as_view(url="/static/favicon.svg", permanent=False)),
    *page_patterns,
    # Any other page URL: the React app renders its "page not found" screen, with a real 404 status.
    re_path(r"^(?!api/|static/).*/$", frontend_not_found),  # slashless URLs are first redirected by APPEND_SLASH
]
