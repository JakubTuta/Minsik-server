import grpc
import pytest


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "gateway"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data


def test_deep_health_endpoint_when_services_healthy(client, mocker):
    mock_stub = mocker.MagicMock()
    mock_stub.GetDataCoverage = mocker.AsyncMock()

    mock_ingestion_client = mocker.MagicMock()
    mock_ingestion_client.stub = mock_stub
    mock_ingestion_client.__aenter__ = mocker.AsyncMock(
        return_value=mock_ingestion_client
    )
    mock_ingestion_client.__aexit__ = mocker.AsyncMock()

    mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

    response = client.get("/health/deep")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "gateway"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data
    assert "dependencies" in data
    assert data["dependencies"]["ingestion_service"] == "healthy"


def test_deep_health_endpoint_when_service_unhealthy(client, mocker):
    import grpc

    async def mock_get_status(*args, **kwargs):
        raise MockRpcError(grpc.StatusCode.UNAVAILABLE, "Service unavailable")

    async def mock_aenter(*args):
        return mock_ingestion_client

    async def mock_aexit(*args):
        pass

    mock_stub = mocker.MagicMock()
    mock_stub.GetDataCoverage = mock_get_status

    mock_ingestion_client = mocker.MagicMock()
    mock_ingestion_client.stub = mock_stub
    mock_ingestion_client.__aenter__ = mock_aenter
    mock_ingestion_client.__aexit__ = mock_aexit

    mocker.patch("app.grpc_clients.IngestionClient", return_value=mock_ingestion_client)

    response = client.get("/health/deep")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["ingestion_service"] == "unhealthy"
