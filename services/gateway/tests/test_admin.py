import pytest
import grpc
import jwt
import datetime
import app.config


def make_token(role: str = "admin", user_id: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    }
    return jwt.encode(payload, app.config.settings.jwt_secret_key, algorithm=app.config.settings.jwt_algorithm)


ADMIN_HEADERS = {"Authorization": f"Bearer {make_token(role='admin')}"}
USER_HEADERS = {"Authorization": f"Bearer {make_token(role='user')}"}


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


class TestTriggerIngestion:
    def test_success(self, client, mocker):
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
            json={"total_books": 100, "source": "both", "language": "en"},
            headers=ADMIN_HEADERS
        )

        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["error"] is None
        assert data["data"]["job_id"] == "test-job-123"
        assert data["data"]["status"] == "pending"
        assert data["data"]["total_books"] == 100

    def test_no_auth(self, client):
        response = client.post(
            "/api/v1/admin/ingestion/trigger",
            json={"total_books": 100, "source": "both", "language": "en"}
        )

        assert response.status_code == 401

    def test_user_role_forbidden(self, client):
        response = client.post(
            "/api/v1/admin/ingestion/trigger",
            json={"total_books": 100, "source": "both", "language": "en"},
            headers=USER_HEADERS
        )

        assert response.status_code == 403

    def test_invalid_request(self, client):
        response = client.post(
            "/api/v1/admin/ingestion/trigger",
            json={"total_books": 0, "source": "both", "language": "en"},
            headers=ADMIN_HEADERS
        )

        assert response.status_code == 422

    def test_invalid_source(self, client):
        response = client.post(
            "/api/v1/admin/ingestion/trigger",
            json={"total_books": 100, "source": "invalid_source", "language": "en"},
            headers=ADMIN_HEADERS
        )

        assert response.status_code == 422

    def test_grpc_error(self, client, mocker):
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
            json={"total_books": 100, "source": "both", "language": "en"},
            headers=ADMIN_HEADERS
        )

        assert response.status_code == 500

        data = response.json()
        assert data["success"] is False
        assert data["error"] is not None
        assert data["error"]["code"] == "INTERNAL_ERROR"


class TestGetIngestionStatus:
    def test_success(self, client, mocker):
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

        response = client.get(
            "/api/v1/admin/ingestion/status/test-job-123",
            headers=ADMIN_HEADERS
        )

        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["data"]["job_id"] == "test-job-123"
        assert data["data"]["status"] == "running"
        assert data["data"]["processed"] == 50
        assert data["data"]["total"] == 100
        assert data["data"]["successful"] == 48
        assert data["data"]["failed"] == 2

    def test_no_auth(self, client):
        response = client.get("/api/v1/admin/ingestion/status/test-job-123")

        assert response.status_code == 401

    def test_user_role_forbidden(self, client):
        response = client.get(
            "/api/v1/admin/ingestion/status/test-job-123",
            headers=USER_HEADERS
        )

        assert response.status_code == 403

    def test_not_found(self, client, mocker):
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

        response = client.get(
            "/api/v1/admin/ingestion/status/nonexistent-job",
            headers=ADMIN_HEADERS
        )

        assert response.status_code == 404

        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"


class TestCancelIngestion:
    def test_success(self, client, mocker):
        mock_response = mocker.MagicMock()
        mock_response.success = True
        mock_response.message = "Job test-job-123 cancelled successfully"

        mock_ingestion_client = mocker.MagicMock()
        mock_ingestion_client.cancel_ingestion = mocker.AsyncMock(return_value=mock_response)
        mock_ingestion_client.__aenter__ = mocker.AsyncMock(return_value=mock_ingestion_client)
        mock_ingestion_client.__aexit__ = mocker.AsyncMock()

        mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

        response = client.delete(
            "/api/v1/admin/ingestion/cancel/test-job-123",
            headers=ADMIN_HEADERS
        )

        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["data"]["success"] is True
        assert "cancelled successfully" in data["data"]["message"]

    def test_no_auth(self, client):
        response = client.delete("/api/v1/admin/ingestion/cancel/test-job-123")

        assert response.status_code == 401

    def test_user_role_forbidden(self, client):
        response = client.delete(
            "/api/v1/admin/ingestion/cancel/test-job-123",
            headers=USER_HEADERS
        )

        assert response.status_code == 403

    def test_not_found(self, client, mocker):
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

        response = client.delete(
            "/api/v1/admin/ingestion/cancel/nonexistent-job",
            headers=ADMIN_HEADERS
        )

        assert response.status_code == 404

        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"
