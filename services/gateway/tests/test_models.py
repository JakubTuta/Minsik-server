import app.models.responses


def test_api_response_success():
    response = app.models.responses.APIResponse(
        success=True, data={"key": "value"}, error=None
    )

    assert response.success is True
    assert response.data == {"key": "value"}
    assert response.error is None


def test_api_response_error():
    error_detail = app.models.responses.ErrorDetail(
        code="TEST_ERROR", message="Test error message", details={"field": "value"}
    )

    response = app.models.responses.APIResponse(
        success=False, data=None, error=error_detail
    )

    assert response.success is False
    assert response.data is None
    assert response.error.code == "TEST_ERROR"
    assert response.error.message == "Test error message"
    assert response.error.details == {"field": "value"}


def test_health_response():
    response = app.models.responses.HealthResponse(
        status="healthy",
        service="gateway",
        version="1.0.0",
        timestamp="2024-01-01T00:00:00",
    )

    assert response.status == "healthy"
    assert response.service == "gateway"
    assert response.version == "1.0.0"
    assert response.timestamp == "2024-01-01T00:00:00"


def test_deep_health_response():
    response = app.models.responses.DeepHealthResponse(
        status="healthy",
        service="gateway",
        version="1.0.0",
        timestamp="2024-01-01T00:00:00",
        dependencies={"ingestion_service": "healthy", "books_service": "healthy"},
    )

    assert response.status == "healthy"
    assert response.dependencies["ingestion_service"] == "healthy"
    assert response.dependencies["books_service"] == "healthy"
