import pytest
import grpc


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


def test_trigger_ingestion_success(client, mocker):
    mock_response = mocker.MagicMock()
    mock_response.job_id = "test-job-123"
    mock_response.status = "pending"
    mock_response.total_books = 100
    mock_response.message = "Ingestion job started: 100 books from both"

    mock_ingestion_client = mocker.MagicMock()
    mock_ingestion_client.trigger_ingestion = mocker.AsyncMock(return_value=mock_response)
    mock_ingestion_client.__aenter__ = mocker.AsyncMock(return_value=mock_ingestion_client)
    mock_ingestion_client.__aexit__ = mocker.AsyncMock()

    mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

    response = client.post(
        "/api/v1/admin/ingestion/trigger",
        json={
            "total_books": 100,
            "source": "both",
            "language": "en"
        }
    )

    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["error"] is None
    assert data["data"]["job_id"] == "test-job-123"
    assert data["data"]["status"] == "pending"
    assert data["data"]["total_books"] == 100


def test_trigger_ingestion_invalid_request(client):
    response = client.post(
        "/api/v1/admin/ingestion/trigger",
        json={
            "total_books": 0,
            "source": "both",
            "language": "en"
        }
    )

    assert response.status_code == 422


def test_trigger_ingestion_invalid_source(client):
    response = client.post(
        "/api/v1/admin/ingestion/trigger",
        json={
            "total_books": 100,
            "source": "invalid_source",
            "language": "en"
        }
    )

    assert response.status_code == 422


def test_trigger_ingestion_grpc_error(client, mocker):
    async def mock_trigger_ingestion(*args, **kwargs):
        raise MockRpcError(grpc.StatusCode.INTERNAL, "Internal server error")

    async def mock_aenter(*args):
        return mock_ingestion_client

    async def mock_aexit(*args):
        pass

    mock_ingestion_client = mocker.MagicMock()
    mock_ingestion_client.trigger_ingestion = mock_trigger_ingestion
    mock_ingestion_client.__aenter__ = mock_aenter
    mock_ingestion_client.__aexit__ = mock_aexit

    mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

    response = client.post(
        "/api/v1/admin/ingestion/trigger",
        json={
            "total_books": 100,
            "source": "both",
            "language": "en"
        }
    )

    assert response.status_code == 500

    data = response.json()
    assert data["success"] is False
    assert data["error"] is not None
    assert data["error"]["code"] == "INTERNAL_ERROR"


def test_get_ingestion_status_success(client, mocker):
    mock_response = mocker.MagicMock()
    mock_response.job_id = "test-job-123"
    mock_response.status = "running"
    mock_response.processed = 50
    mock_response.total = 100
    mock_response.successful = 48
    mock_response.failed = 2
    mock_response.error = ""
    mock_response.started_at = 1704067200
    mock_response.completed_at = 0

    mock_ingestion_client = mocker.MagicMock()
    mock_ingestion_client.get_ingestion_status = mocker.AsyncMock(return_value=mock_response)
    mock_ingestion_client.__aenter__ = mocker.AsyncMock(return_value=mock_ingestion_client)
    mock_ingestion_client.__aexit__ = mocker.AsyncMock()

    mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

    response = client.get("/api/v1/admin/ingestion/status/test-job-123")

    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["data"]["job_id"] == "test-job-123"
    assert data["data"]["status"] == "running"
    assert data["data"]["processed"] == 50
    assert data["data"]["total"] == 100
    assert data["data"]["successful"] == 48
    assert data["data"]["failed"] == 2


def test_get_ingestion_status_not_found(client, mocker):
    async def mock_get_status(*args, **kwargs):
        raise MockRpcError(grpc.StatusCode.NOT_FOUND, "Job not found")

    async def mock_aenter(*args):
        return mock_ingestion_client

    async def mock_aexit(*args):
        pass

    mock_ingestion_client = mocker.MagicMock()
    mock_ingestion_client.get_ingestion_status = mock_get_status
    mock_ingestion_client.__aenter__ = mock_aenter
    mock_ingestion_client.__aexit__ = mock_aexit

    mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

    response = client.get("/api/v1/admin/ingestion/status/nonexistent-job")

    assert response.status_code == 404

    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "NOT_FOUND"


def test_cancel_ingestion_success(client, mocker):
    mock_response = mocker.MagicMock()
    mock_response.success = True
    mock_response.message = "Job test-job-123 cancelled successfully"

    mock_ingestion_client = mocker.MagicMock()
    mock_ingestion_client.cancel_ingestion = mocker.AsyncMock(return_value=mock_response)
    mock_ingestion_client.__aenter__ = mocker.AsyncMock(return_value=mock_ingestion_client)
    mock_ingestion_client.__aexit__ = mocker.AsyncMock()

    mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

    response = client.delete("/api/v1/admin/ingestion/cancel/test-job-123")

    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["data"]["success"] is True
    assert "cancelled successfully" in data["data"]["message"]


def test_cancel_ingestion_not_found(client, mocker):
    async def mock_cancel(*args, **kwargs):
        raise MockRpcError(grpc.StatusCode.NOT_FOUND, "Job not found")

    async def mock_aenter(*args):
        return mock_ingestion_client

    async def mock_aexit(*args):
        pass

    mock_ingestion_client = mocker.MagicMock()
    mock_ingestion_client.cancel_ingestion = mock_cancel
    mock_ingestion_client.__aenter__ = mock_aenter
    mock_ingestion_client.__aexit__ = mock_aexit

    mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

    response = client.delete("/api/v1/admin/ingestion/cancel/nonexistent-job")

    assert response.status_code == 404

    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "NOT_FOUND"
