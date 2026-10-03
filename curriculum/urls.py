from django.urls import path

from curriculum.views import SyllabusView, TopicDetailView

urlpatterns = [
    path("documents/<int:document_id>/syllabus/", SyllabusView.as_view(), name="syllabus"),
    path("topics/<int:pk>/", TopicDetailView.as_view(), name="topic-detail"),
]
