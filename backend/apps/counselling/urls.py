from django.urls import path

from . import views

urlpatterns = [
    path("sessions/", views.SessionListCreateView.as_view(), name="session-list"),
    path("sessions/<str:session_id>/", views.SessionDetailView.as_view(), name="session-detail"),
    path("sessions/<str:session_id>/complete/", views.SessionCompleteView.as_view(), name="session-complete"),
    path("sessions/<str:session_id>/cancel/", views.SessionCancelView.as_view(), name="session-cancel"),
    path("sessions/<str:session_id>/follow-up/", views.FollowUpUpdateView.as_view(), name="session-follow-up"),
    path("follow-ups/", views.FollowUpListView.as_view(), name="follow-up-list"),
    path("calendar/", views.CalendarView.as_view(), name="counselling-calendar"),
]
