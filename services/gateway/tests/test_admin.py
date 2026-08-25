import datetime
import re

import app.config
import app.main
import grpc
import jwt
import pytest


def make_token(role: str = "admin", user_id: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=15),
    }
    return jwt.encode(
        payload,
        app.config.settings.jwt_secret_key,
        algorithm=app.config.settings.jwt_algorithm,
    )


ADMIN_HEADERS = {"Authorization": f"Bearer {make_token(role='admin')}"}
USER_HEADERS = {"Authorization": f"Bearer {make_token(role='user')}"}


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details=""):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


def _admin_routes():
    """Every mounted admin route, so a new one added without a guard fails here.

    Enumerated from the app rather than listed by hand: a hand-written list
    only ever covers the routes someone remembered to add to it, which is the
    same gap it is meant to close.
    """
    routes = []
    for route in app.main.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/admin"):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            routes.append((method, path))
    return sorted(routes)


def _fill(path: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: "1" if m.group(1).endswith("_id") else "x", path)


ADMIN_ROUTES = _admin_routes()


def _call(client, method, path, **kwargs):
    if method in ("POST", "PUT", "PATCH"):
        kwargs.setdefault("json", {})
    return client.request(method, _fill(path), **kwargs)


def test_admin_route_list_is_not_empty():
    assert len(ADMIN_ROUTES) > 10


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_route_rejects_anonymous(client, method, path):
    assert _call(client, method, path).status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_route_rejects_non_admin(client, method, path):
    assert _call(client, method, path, headers=USER_HEADERS).status_code == 403


class TestDataCoverage:
    def test_returns_counts(self, client, mock_ingestion_client, mocker):
        coverage = mocker.MagicMock()
        coverage.db_books_count = 12453
        coverage.db_authors_count = 8721
        coverage.db_series_count = 342
        coverage.cached = False
        mock_ingestion_client.get_data_coverage = mocker.AsyncMock(
            return_value=coverage
        )

        response = client.get(
            "/api/v1/admin/ingestion/coverage", headers=ADMIN_HEADERS
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["db_books_count"] == 12453
        assert body["data"]["cached"] is False

    def test_upstream_failure_is_a_500_envelope(
        self, client, mock_ingestion_client, mocker
    ):
        mock_ingestion_client.get_data_coverage = mocker.AsyncMock(
            side_effect=MockRpcError(grpc.StatusCode.UNAVAILABLE, "down")
        )

        response = client.get(
            "/api/v1/admin/ingestion/coverage", headers=ADMIN_HEADERS
        )

        assert response.status_code == 500
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "INTERNAL_ERROR"


class TestDeleteBook:
    def test_deletes_and_reports_the_message(
        self, client, mock_books_client, mocker
    ):
        result = mocker.MagicMock()
        result.message = "Book 1 deleted"
        mock_books_client.delete_book = mocker.AsyncMock(return_value=result)

        response = client.delete("/api/v1/admin/books/1", headers=ADMIN_HEADERS)

        assert response.status_code == 200
        assert response.json()["data"]["message"] == "Book 1 deleted"
        mock_books_client.delete_book.assert_awaited_once_with(book_id=1)

    def test_missing_book_is_a_404_envelope(self, client, mock_books_client, mocker):
        mock_books_client.delete_book = mocker.AsyncMock(
            side_effect=MockRpcError(grpc.StatusCode.NOT_FOUND, "Book not found")
        )

        response = client.delete("/api/v1/admin/books/999", headers=ADMIN_HEADERS)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestDeleteAuthor:
    def test_deletes_and_reports_the_message(
        self, client, mock_books_client, mocker
    ):
        result = mocker.MagicMock()
        result.message = "Author 1 deleted"
        mock_books_client.delete_author = mocker.AsyncMock(return_value=result)

        response = client.delete("/api/v1/admin/authors/1", headers=ADMIN_HEADERS)

        assert response.status_code == 200
        mock_books_client.delete_author.assert_awaited_once_with(author_id=1)

    def test_missing_author_is_a_404_envelope(
        self, client, mock_books_client, mocker
    ):
        mock_books_client.delete_author = mocker.AsyncMock(
            side_effect=MockRpcError(grpc.StatusCode.NOT_FOUND, "Author not found")
        )

        response = client.delete("/api/v1/admin/authors/999", headers=ADMIN_HEADERS)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestAuditBooks:
    def test_passes_filters_through(self, client, mock_books_client, mocker):
        item = mocker.MagicMock()
        item.book_id = 1
        item.title = "Suspicious Book"
        item.slug = "suspicious-book"
        item.language = "en"
        item.primary_cover_url = ""
        item.author_count = 0
        item.genre_count = 0
        item.original_publication_year = 1200
        item.issues = ["missing_cover"]

        audit_response = mocker.MagicMock()
        audit_response.items = [item]
        mock_books_client.audit_books = mocker.AsyncMock(return_value=audit_response)

        response = client.get(
            "/api/v1/admin/quality/books",
            params={"limit": 5, "check_missing_cover": True, "language": "en"},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 200
        kwargs = mock_books_client.audit_books.await_args.kwargs
        assert kwargs["limit"] == 5
        assert kwargs["check_missing_cover"] is True
        assert kwargs["language"] == "en"
