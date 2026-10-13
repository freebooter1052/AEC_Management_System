from django.urls import path
from django.views.generic import RedirectView, TemplateView


def page(template):
    return TemplateView.as_view(template_name=f"frontend/{template}")


# Pages are static shells; data is loaded from the REST API with the user's
# bearer token, and every permission is enforced by the API itself.
urlpatterns = [
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("login/", page("login.html"), name="login"),
    path("register/", page("register.html"), name="register"),
    path("dashboard/", page("dashboard.html"), name="dashboard"),
    path("profile/", page("profile.html"), name="profile"),
    path("students/", page("students.html"), name="students"),
    path("students/<str:student_id>/", page("profile.html"), name="student-profile"),
    path("counsellors/", page("counsellors.html"), name="counsellors"),
    path("universities/", page("universities.html"), name="universities"),
]
