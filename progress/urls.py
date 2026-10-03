from django.urls import path

from progress.views import QuizAttemptView, StepCheckView

urlpatterns = [
    path("steps/<int:pk>/check/", StepCheckView.as_view(), name="step-check"),
    path("quizzes/<int:pk>/attempts/", QuizAttemptView.as_view(), name="quiz-attempt"),
]
