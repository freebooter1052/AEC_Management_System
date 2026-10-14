from django.urls import path

from . import views

urlpatterns = [
    path("", views.DocumentListCreateView.as_view(), name="document-list"),
    path("checklist/", views.DocumentChecklistView.as_view(), name="document-checklist"),
    path("summary/", views.DocumentSummaryView.as_view(), name="document-summary"),
    path("<str:document_id>/", views.DocumentDetailView.as_view(), name="document-detail"),
    path("<str:document_id>/upload/", views.DocumentUploadView.as_view(), name="document-upload"),
    path("<str:document_id>/verify/", views.DocumentReviewView.as_view(), name="document-verify"),
    path("<str:document_id>/file/", views.DocumentFileView.as_view(), name="document-file"),
]
