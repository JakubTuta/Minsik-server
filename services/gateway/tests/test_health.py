import grpc

_CLIENT_PATHS = (
    "app.grpc_clients.ingestion_client",
    "app.grpc_clients.books_client",
    "app.grpc_clients.auth_client",
    "app.grpc_clients.user_data_client",
    "app.grpc_clients.recommendation_client",
)

_DEPENDENCY_NAMES = (
    "ingestion_service",
    "books_service",
    "auth_service",
    "user_data_service",
    "recommendation_service",
)


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


def _patch_health(mocker, results):
    """Point every dependency's health_check at the given per-client result.

    The route reads the module-level clients once at import time, so patching
    the attribute on the client object is what the route actually sees.
    """
    for path, result in zip(_CLIENT_PATHS, results):
        if isinstance(result, Exception):
            mocker.patch(f"{path}.health_check", side_effect=result)
        else:
            mocker.patch(f"{path}.health_check", return_value=result)


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "gateway"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data


def test_deep_health_endpoint_when_services_healthy(client, mocker):
    _patch_health(mocker, [True] * len(_CLIENT_PATHS))

    response = client.get("/health/deep")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "gateway"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data
    for name in _DEPENDENCY_NAMES:
        assert data["dependencies"][name] == "healthy"


def test_deep_health_endpoint_when_service_unhealthy(client, mocker):
    _patch_health(
        mocker,
        [MockRpcError(grpc.StatusCode.UNAVAILABLE, "Service unavailable")]
        + [True] * (len(_CLIENT_PATHS) - 1),
    )

    response = client.get("/health/deep")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["ingestion_service"] == "unhealthy"
    assert data["dependencies"]["books_service"] == "healthy"


def test_deep_health_reports_every_backing_service(client, mocker):
    _patch_health(mocker, [True, True, True, False, True])

    response = client.get("/health/deep")

    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["user_data_service"] == "unhealthy"
