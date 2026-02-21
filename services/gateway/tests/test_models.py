import app.models.requests
import app.models.responses
import pydantic
import pytest


def test_trigger_ingestion_request_valid():
    request = app.models.requests.TriggerIngestionRequest(
        total_books=100, source="both", language="en"
    )

    assert request.total_books == 100
    assert request.source == "both"
    assert request.language == "en"


def test_trigger_ingestion_request_defaults():
    request = app.models.requests.TriggerIngestionRequest(total_books=50)

    assert request.total_books == 50
    assert request.source == "both"
    assert request.language == "en"


def test_trigger_ingestion_request_invalid_total_books():
    with pytest.raises(pydantic.ValidationError) as exc_info:
        app.models.requests.TriggerIngestionRequest(total_books=0)

    assert "total_books" in str(exc_info.value)


def test_trigger_ingestion_request_invalid_source():
    with pytest.raises(pydantic.ValidationError) as exc_info:
        app.models.requests.TriggerIngestionRequest(
            total_books=100, source="invalid_source"
        )

    assert "source" in str(exc_info.value)


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


def test_ingestion_status_response():
    response = app.models.requests.IngestionStatusResponse(
        job_id="test-job-123",
        status="running",
        processed=50,
        total=100,
        successful=48,
        failed=2,
        error="",
        started_at=1704067200,
        completed_at=0,
    )

    assert response.job_id == "test-job-123"
    assert response.status == "running"
    assert response.processed == 50
    assert response.total == 100
    assert response.successful == 48
    assert response.failed == 2
    assert response.started_at == 1704067200
    assert response.completed_at == 0


def test_trigger_ingestion_response():
    response = app.models.requests.TriggerIngestionResponse(
        job_id="test-job-123",
        status="pending",
        total_books=100,
        processed=0,
        successful=0,
        failed=0,
        error_message=None,
    )

    assert response.job_id == "test-job-123"
    assert response.status == "pending"
    assert response.total_books == 100
    assert response.processed == 0
    assert response.successful == 0
    assert response.failed == 0
    assert response.error_message is None


def test_cancel_ingestion_response():
    response = app.models.requests.CancelIngestionResponse(
        success=True, message="Job cancelled successfully"
    )

    assert response.success is True
    assert response.message == "Job cancelled successfully"
    assert isinstance(response.message, str)
