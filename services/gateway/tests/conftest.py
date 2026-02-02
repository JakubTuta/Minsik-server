import pytest
import fastapi.testclient
import app.main
import app.grpc_clients


@pytest.fixture
def client():
    return fastapi.testclient.TestClient(app.main.app)


@pytest.fixture
def mock_ingestion_client(mocker):
    mock_client = mocker.MagicMock()
    mocker.patch.object(app.grpc_clients, "ingestion_client", mock_client)
    return mock_client
