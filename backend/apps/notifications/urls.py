from django.urls import path

from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("unread-count/", views.UnreadCountView.as_view(), name="notification-unread-count"),
    path("read-all/", views.MarkAllReadView.as_view(), name="notification-read-all"),
    path("<str:notification_id>/", views.NotificationDetailView.as_view(), name="notification-detail"),
    path("<str:notification_id>/read/", views.NotificationReadView.as_view(), name="notification-read"),
]
