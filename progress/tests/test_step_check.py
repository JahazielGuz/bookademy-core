"""The Check button, over HTTP."""

import pytest

from progress.models import StepCompletion


@pytest.mark.django_db
def test_correct_code_passes_and_records_the_completion(api, course, learner):
    step = course["steps"][0]
    response = api.post(
        f"/api/steps/{step.id}/check/", {"code": step.expected_code}, format="json"
    )

    assert response.status_code == 200
    assert response.data["passed"] is True
    assert response.data["next_step_id"] == course["steps"][1].id
    assert StepCompletion.objects.filter(user=learner, step=step).exists()


@pytest.mark.django_db
def test_wrong_code_fails_and_points_at_the_line(api, course, learner):
    step = course["steps"][0]
    response = api.post(
        f"/api/steps/{step.id}/check/",
        {"code": "def favorite_color():\n    color = 'Blue'"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["passed"] is False
    assert response.data["first_mismatch_line"] == 2
    # No Next until it passes.
    assert response.data["next_step_id"] is None
    assert not StepCompletion.objects.filter(user=learner, step=step).exists()


@pytest.mark.django_db
def test_a_later_step_cannot_be_checked_before_the_one_before_it(api, course):
    second = course["steps"][1]
    response = api.post(
        f"/api/steps/{second.id}/check/", {"code": second.expected_code}, format="json"
    )

    assert response.status_code == 409


@pytest.mark.django_db
def test_the_second_step_opens_once_the_first_is_passed(api, course):
    first, second = course["steps"]
    api.post(f"/api/steps/{first.id}/check/", {"code": first.expected_code}, format="json")

    response = api.post(
        f"/api/steps/{second.id}/check/", {"code": second.expected_code}, format="json"
    )

    assert response.status_code == 200
    assert response.data["passed"] is True
    assert response.data["next_step_id"] is None


@pytest.mark.django_db
def test_rechecking_a_passed_step_does_not_duplicate_the_row(api, course, learner):
    step = course["steps"][0]
    for _ in range(3):
        api.post(f"/api/steps/{step.id}/check/", {"code": step.expected_code}, format="json")

    assert StepCompletion.objects.filter(user=learner, step=step).count() == 1


@pytest.mark.django_db
def test_another_learners_step_is_not_found(course, stranger):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=stranger)
    step = course["steps"][0]

    response = client.post(
        f"/api/steps/{step.id}/check/", {"code": step.expected_code}, format="json"
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_signing_out_closes_the_endpoint(course):
    from rest_framework.test import APIClient

    step = course["steps"][0]
    response = APIClient().post(f"/api/steps/{step.id}/check/", {"code": ""}, format="json")

    assert response.status_code == 401
