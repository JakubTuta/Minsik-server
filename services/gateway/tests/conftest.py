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


@pytest.fixture
def mock_auth_client(mocker):
    mock_client = mocker.MagicMock()
    mock_client.register = mocker.AsyncMock()
    mock_client.login = mocker.AsyncMock()
    mock_client.logout = mocker.AsyncMock()
    mock_client.refresh_token = mocker.AsyncMock()
    mock_client.get_current_user = mocker.AsyncMock()
    mock_client.update_profile = mocker.AsyncMock()
    mocker.patch.object(app.grpc_clients, "auth_client", mock_client)
    return mock_client


@pytest.fixture
def mock_books_client(mocker):
    mock_client = mocker.MagicMock()
    for method in [
        "search_books_and_authors", "get_book", "get_author", "get_author_books",
        "get_series", "get_series_books",
    ]:
        setattr(mock_client, method, mocker.AsyncMock())
    mocker.patch.object(app.grpc_clients, "books_client", mock_client)
    return mock_client
