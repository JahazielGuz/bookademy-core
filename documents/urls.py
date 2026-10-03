from django.urls import path

from documents.views import DocumentDetailView, DocumentEventsView, DocumentListCreateView

urlpatterns = [
    path("documents/", DocumentListCreateView.as_view(), name="document-list"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("documents/<int:pk>/events/", DocumentEventsView.as_view(), name="document-events"),
]
