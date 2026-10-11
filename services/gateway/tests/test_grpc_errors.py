import json
from unittest.mock import AsyncMock

import app.grpc_clients
import app.utils.grpc_errors
import grpc
import pytest


class FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode, details: str):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


@pytest.mark.parametrize(
    ("status", "http_status", "error_code"),
    [
        (grpc.StatusCode.NOT_FOUND, 404, "NOT_FOUND"),
        (grpc.StatusCode.INVALID_ARGUMENT, 400, "INVALID_ARGUMENT"),
        (grpc.StatusCode.ALREADY_EXISTS, 409, "ALREADY_EXISTS"),
        (grpc.StatusCode.PERMISSION_DENIED, 403, "PERMISSION_DENIED"),
        (grpc.StatusCode.UNAVAILABLE, 503, "SERVICE_UNAVAILABLE"),
        (grpc.StatusCode.DEADLINE_EXCEEDED, 504, "UPSTREAM_TIMEOUT"),
        (grpc.StatusCode.INTERNAL, 500, "INTERNAL_ERROR"),
        (grpc.StatusCode.UNKNOWN, 500, "INTERNAL_ERROR"),
    ],
)
def test_status_codes_map_to_http(status, http_status, error_code):
    mapped_status, mapped_code, _ = app.utils.grpc_errors.to_http_error(
        FakeRpcError(status, "x")
    )

    assert (mapped_status, mapped_code) == (http_status, error_code)


def test_caller_mistakes_keep_the_service_message():
    _, _, message = app.utils.grpc_errors.to_http_error(
        FakeRpcError(grpc.StatusCode.NOT_FOUND, "Book not found: dune")
    )

    assert message == "Book not found: dune"


@pytest.mark.parametrize(
    "status",
    [grpc.StatusCode.INTERNAL, grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.UNKNOWN],
)
def test_server_side_failures_never_expose_the_exception_text(status):
    _, _, message = app.utils.grpc_errors.to_http_error(
        FakeRpcError(status, 'relation "books.books" does not exist')
    )

    assert "relation" not in message


def test_an_unhandled_rpc_error_becomes_an_enveloped_response(client, monkeypatch):
    monkeypatch.setattr(
        app.grpc_clients.books_client,
        "get_book",
        AsyncMock(
            side_effect=FakeRpcError(grpc.StatusCode.UNAVAILABLE, "connect failed")
        ),
    )

    response = client.get("/api/v1/books/dune")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "connect failed" not in json.dumps(body)
