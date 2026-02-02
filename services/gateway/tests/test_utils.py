import pytest
import app.utils.responses


def test_success_response_default_status():
    response = app.utils.responses.success_response({"key": "value"})

    assert response.status_code == 200

    body = response.body.decode()
    assert '"success":true' in body or '"success": true' in body
    assert '"key"' in body
    assert '"value"' in body


def test_success_response_custom_status():
    response = app.utils.responses.success_response({"created": True}, status_code=201)

    assert response.status_code == 201

    body = response.body.decode()
    assert '"success":true' in body or '"success": true' in body
    assert '"created"' in body


def test_error_response_default_status():
    response = app.utils.responses.error_response(
        code="TEST_ERROR",
        message="Test error message"
    )

    assert response.status_code == 400

    body = response.body.decode()
    assert '"success":false' in body or '"success": false' in body
    assert '"TEST_ERROR"' in body
    assert '"Test error message"' in body


def test_error_response_with_details():
    response = app.utils.responses.error_response(
        code="VALIDATION_ERROR",
        message="Validation failed",
        details={"field": "email", "issue": "invalid format"},
        status_code=422
    )

    assert response.status_code == 422

    body = response.body.decode()
    assert '"success":false' in body or '"success": false' in body
    assert '"VALIDATION_ERROR"' in body
    assert '"field"' in body
    assert '"email"' in body


def test_error_response_custom_status():
    response = app.utils.responses.error_response(
        code="SERVER_ERROR",
        message="Internal server error",
        status_code=500
    )

    assert response.status_code == 500

    body = response.body.decode()
    assert '"success":false' in body or '"success": false' in body
    assert '"SERVER_ERROR"' in body
