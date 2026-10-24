from django.urls import path

from . import views

urlpatterns = [
    path("", views.WorkspaceView.as_view(), name="writing-workspace"),
    path("consent/", views.ConsentView.as_view(), name="writing-consent"),
    path("consent/request/", views.ConsentRequestView.as_view(), name="writing-consent-request"),
    path("settings/", views.SettingsView.as_view(), name="writing-settings"),
    path("statements/", views.StatementCreateView.as_view(), name="statement-create"),
    path("statements/<str:statement_id>/", views.StatementDetailView.as_view(), name="statement-detail"),
    path("statements/<str:statement_id>/<str:action>/", views.StatementActionView.as_view(), name="statement-action"),
    path("references/", views.ReferenceCreateView.as_view(), name="reference-create"),
    path("references/<str:reference_id>/", views.ReferenceDetailView.as_view(), name="reference-detail"),
    path("references/<str:reference_id>/decision/", views.ReferenceDecisionView.as_view(), name="reference-decision"),
    path("references/<str:reference_id>/prepare/", views.ReferencePrepareView.as_view(), name="reference-prepare"),
]
