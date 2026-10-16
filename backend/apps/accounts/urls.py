from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="auth-register"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path("change-password/", views.ChangePasswordView.as_view(), name="auth-change-password"),
    path("forgot-password/", views.ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("verify-reset-code/", views.VerifyResetCodeView.as_view(), name="auth-verify-reset-code"),
    path("reset-password/", views.ResetPasswordView.as_view(), name="auth-reset-password"),
    path("users/", views.UserListView.as_view(), name="auth-users"),
    path("users/<str:user_id>/", views.UserDetailView.as_view(), name="auth-user-detail"),
]
