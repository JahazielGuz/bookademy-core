import pytest


@pytest.mark.django_db
def test_all_correct_passes_and_reveals_the_answers(api, course):
    quiz = course["quiz"]
    questions = list(quiz.questions.all())
    answers = {str(question.id): question.correct_index for question in questions}

    response = api.post(f"/api/quizzes/{quiz.id}/attempts/", {"answers": answers}, format="json")

    assert response.status_code == 201
    assert response.data["score"] == 2
    assert response.data["total"] == 2
    assert response.data["passed"] is True
    assert all(result["correct"] for result in response.data["results"])
    assert all(len(result["explanation"]) > 0 for result in response.data["results"])


@pytest.mark.django_db
def test_one_wrong_answer_does_not_pass(api, course):
    quiz = course["quiz"]
    questions = list(quiz.questions.all())
    answers = {str(questions[0].id): 1, str(questions[1].id): questions[1].correct_index}

    response = api.post(f"/api/quizzes/{quiz.id}/attempts/", {"answers": answers}, format="json")

    assert response.data["score"] == 1
    assert response.data["passed"] is False


@pytest.mark.django_db
def test_a_partial_submission_is_rejected(api, course):
    quiz = course["quiz"]
    first = quiz.questions.first()

    response = api.post(
        f"/api/quizzes/{quiz.id}/attempts/",
        {"answers": {str(first.id): first.correct_index}},
        format="json",
    )

    assert response.status_code == 400
