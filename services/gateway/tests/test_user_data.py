import datetime
import pytest
import grpc
import jwt
import app.config
import app.grpc_clients


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


def make_token(user_id: int = 1, role: str = "user") -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    }
    return jwt.encode(payload, app.config.settings.jwt_secret_key, algorithm=app.config.settings.jwt_algorithm)


USER_HEADERS = {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def mock_user_data_client(mocker):
    mock_client = mocker.MagicMock()
    for method in [
        "upsert_bookshelf", "get_user_bookshelves", "get_public_bookshelves",
        "toggle_favourite", "get_user_favourites",
        "upsert_rating", "delete_rating", "get_user_ratings",
        "get_book_comments", "create_comment", "update_comment", "delete_comment", "get_user_comments",
        "get_book_notes", "create_note", "update_note", "delete_note", "get_user_notes",
    ]:
        setattr(mock_client, method, mocker.AsyncMock())
    mocker.patch.object(app.grpc_clients, "user_data_client", mock_client)
    return mock_client


def _bookshelf(mocker):
    b = mocker.MagicMock()
    b.bookshelf_id = 1
    b.user_id = 1
    b.book_id = 100
    b.book_slug = "the-hobbit"
    b.book_title = "The Hobbit"
    b.book_cover_url = ""
    b.status = "reading"
    b.is_favorite = False
    b.created_at = "2026-01-01T00:00:00"
    b.updated_at = "2026-01-01T00:00:00"
    return b


def _rating(mocker):
    r = mocker.MagicMock()
    r.rating_id = 1
    r.user_id = 1
    r.book_id = 100
    r.book_slug = "the-hobbit"
    r.book_title = "The Hobbit"
    r.book_cover_url = ""
    r.overall_rating = 4.5
    r.review_text = "Great book"
    r.pacing = 0.0
    r.has_pacing = False
    r.emotional_impact = 0.0
    r.has_emotional_impact = False
    r.intellectual_depth = 0.0
    r.has_intellectual_depth = False
    r.writing_quality = 0.0
    r.has_writing_quality = False
    r.rereadability = 0.0
    r.has_rereadability = False
    r.created_at = "2026-01-01T00:00:00"
    r.updated_at = "2026-01-01T00:00:00"
    return r


def _comment(mocker):
    c = mocker.MagicMock()
    c.comment_id = 1
    c.user_id = 1
    c.book_id = 100
    c.book_slug = "the-hobbit"
    c.body = "Loved it!"
    c.is_spoiler = False
    c.created_at = "2026-01-01T00:00:00"
    c.updated_at = "2026-01-01T00:00:00"
    return c


def _note(mocker):
    n = mocker.MagicMock()
    n.note_id = 1
    n.user_id = 1
    n.book_id = 100
    n.book_slug = "the-hobbit"
    n.note_text = "Remember this"
    n.page_number = 42
    n.has_page_number = True
    n.is_spoiler = False
    n.created_at = "2026-01-01T00:00:00"
    n.updated_at = "2026-01-01T00:00:00"
    return n


class TestBookshelfEndpoints:
    def test_upsert_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.bookshelf = _bookshelf(mocker)
        mock_user_data_client.upsert_bookshelf.return_value = resp_obj
        resp = client.put(
            "/api/v1/users/me/bookshelves/the-hobbit",
            json={"status": "reading"},
            headers=USER_HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["bookshelf"]["status"] == "reading"

    def test_upsert_requires_auth(self, client, mock_user_data_client):
        resp = client.put("/api/v1/users/me/bookshelves/the-hobbit", json={"status": "reading"})
        assert resp.status_code == 401

    def test_upsert_invalid_status_rejected(self, client, mock_user_data_client):
        resp = client.put(
            "/api/v1/users/me/bookshelves/the-hobbit",
            json={"status": "bad_value"},
            headers=USER_HEADERS
        )
        assert resp.status_code == 422

    def test_upsert_book_not_found(self, client, mock_user_data_client):
        mock_user_data_client.upsert_bookshelf.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "book not found"
        )
        resp = client.put(
            "/api/v1/users/me/bookshelves/unknown",
            json={"status": "reading"},
            headers=USER_HEADERS
        )
        assert resp.status_code == 404

    def test_get_bookshelves_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.bookshelves = [_bookshelf(mocker)]
        resp_obj.total_count = 1
        mock_user_data_client.get_user_bookshelves.return_value = resp_obj
        resp = client.get("/api/v1/users/me/bookshelves", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_count"] == 1
        assert len(resp.json()["data"]["items"]) == 1

    def test_get_bookshelves_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/bookshelves").status_code == 401

    def test_get_bookshelves_status_filter_forwarded(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.bookshelves = []
        resp_obj.total_count = 0
        mock_user_data_client.get_user_bookshelves.return_value = resp_obj
        client.get("/api/v1/users/me/bookshelves?status=reading", headers=USER_HEADERS)
        _, kwargs = mock_user_data_client.get_user_bookshelves.call_args
        assert kwargs["status_filter"] == "reading"

    def test_get_bookshelves_grpc_internal(self, client, mock_user_data_client):
        mock_user_data_client.get_user_bookshelves.side_effect = MockRpcError(
            grpc.StatusCode.INTERNAL, "error"
        )
        assert client.get("/api/v1/users/me/bookshelves", headers=USER_HEADERS).status_code == 500


class TestFavouriteEndpoints:
    def test_add_favourite_success(self, client, mock_user_data_client, mocker):
        r = mocker.MagicMock()
        r.is_favorite = True
        r.book_id = 100
        r.book_slug = "the-hobbit"
        mock_user_data_client.toggle_favourite.return_value = r
        resp = client.post("/api/v1/books/the-hobbit/favourite", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_favorite"] is True
        _, kwargs = mock_user_data_client.toggle_favourite.call_args
        assert kwargs["is_favorite"] is True

    def test_remove_favourite_success(self, client, mock_user_data_client, mocker):
        r = mocker.MagicMock()
        r.is_favorite = False
        r.book_id = 100
        r.book_slug = "the-hobbit"
        mock_user_data_client.toggle_favourite.return_value = r
        resp = client.delete("/api/v1/books/the-hobbit/favourite", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_favorite"] is False
        _, kwargs = mock_user_data_client.toggle_favourite.call_args
        assert kwargs["is_favorite"] is False

    def test_favourite_requires_auth(self, client, mock_user_data_client):
        assert client.post("/api/v1/books/the-hobbit/favourite").status_code == 401

    def test_favourite_book_not_found(self, client, mock_user_data_client):
        mock_user_data_client.toggle_favourite.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert client.post("/api/v1/books/unknown/favourite", headers=USER_HEADERS).status_code == 404

    def test_get_favourites_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.bookshelves = []
        resp_obj.total_count = 0
        mock_user_data_client.get_user_favourites.return_value = resp_obj
        assert client.get("/api/v1/users/me/favourites", headers=USER_HEADERS).status_code == 200

    def test_get_favourites_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/favourites").status_code == 401


class TestRatingEndpoints:
    def test_upsert_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.rating = _rating(mocker)
        mock_user_data_client.upsert_rating.return_value = resp_obj
        resp = client.post(
            "/api/v1/books/the-hobbit/rate",
            json={"overall_rating": 4.5, "review_text": "Great!"},
            headers=USER_HEADERS
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["rating"]["overall_rating"] == 4.5

    def test_upsert_requires_auth(self, client, mock_user_data_client):
        assert client.post("/api/v1/books/the-hobbit/rate", json={"overall_rating": 4.0}).status_code == 401

    def test_upsert_missing_overall_rating_rejected(self, client, mock_user_data_client):
        assert client.post(
            "/api/v1/books/the-hobbit/rate", json={}, headers=USER_HEADERS
        ).status_code == 422

    def test_upsert_out_of_range_rejected(self, client, mock_user_data_client):
        assert client.post(
            "/api/v1/books/the-hobbit/rate",
            json={"overall_rating": 6.0},
            headers=USER_HEADERS
        ).status_code == 422

    def test_upsert_below_range_rejected(self, client, mock_user_data_client):
        assert client.post(
            "/api/v1/books/the-hobbit/rate",
            json={"overall_rating": 0.5},
            headers=USER_HEADERS
        ).status_code == 422

    def test_upsert_book_not_found(self, client, mock_user_data_client):
        mock_user_data_client.upsert_rating.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert client.post(
            "/api/v1/books/unknown/rate",
            json={"overall_rating": 4.0},
            headers=USER_HEADERS
        ).status_code == 404

    def test_delete_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.delete_rating.return_value = mocker.MagicMock()
        assert client.delete("/api/v1/books/the-hobbit/rate", headers=USER_HEADERS).status_code == 204

    def test_delete_requires_auth(self, client, mock_user_data_client):
        assert client.delete("/api/v1/books/the-hobbit/rate").status_code == 401

    def test_delete_not_found(self, client, mock_user_data_client):
        mock_user_data_client.delete_rating.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert client.delete("/api/v1/books/the-hobbit/rate", headers=USER_HEADERS).status_code == 404

    def test_get_ratings_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.ratings = [_rating(mocker)]
        resp_obj.total_count = 1
        mock_user_data_client.get_user_ratings.return_value = resp_obj
        resp = client.get("/api/v1/users/me/ratings", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_count"] == 1

    def test_get_ratings_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/ratings").status_code == 401


class TestCommentEndpoints:
    def test_get_book_comments_is_public(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.comments = [_comment(mocker)]
        resp_obj.total_count = 1
        mock_user_data_client.get_book_comments.return_value = resp_obj
        resp = client.get("/api/v1/books/the-hobbit/comments")
        assert resp.status_code == 200
        assert resp.json()["data"]["total_count"] == 1

    def test_get_book_comments_no_auth_needed(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.comments = []
        resp_obj.total_count = 0
        mock_user_data_client.get_book_comments.return_value = resp_obj
        assert client.get("/api/v1/books/the-hobbit/comments").status_code == 200

    def test_get_book_comments_include_spoilers_forwarded(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.comments = []
        resp_obj.total_count = 0
        mock_user_data_client.get_book_comments.return_value = resp_obj
        client.get("/api/v1/books/the-hobbit/comments?include_spoilers=true")
        _, kwargs = mock_user_data_client.get_book_comments.call_args
        assert kwargs["include_spoilers"] is True

    def test_create_comment_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.comment = _comment(mocker)
        mock_user_data_client.create_comment.return_value = resp_obj
        resp = client.post(
            "/api/v1/books/the-hobbit/comments",
            json={"body": "Loved it!", "is_spoiler": False},
            headers=USER_HEADERS
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["comment"]["body"] == "Loved it!"

    def test_create_comment_requires_auth(self, client, mock_user_data_client):
        assert client.post(
            "/api/v1/books/the-hobbit/comments", json={"body": "Hi"}
        ).status_code == 401

    def test_create_comment_empty_body_rejected(self, client, mock_user_data_client):
        assert client.post(
            "/api/v1/books/the-hobbit/comments",
            json={"body": ""},
            headers=USER_HEADERS
        ).status_code == 422

    def test_update_comment_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.comment = _comment(mocker)
        mock_user_data_client.update_comment.return_value = resp_obj
        assert client.put(
            "/api/v1/books/the-hobbit/comments/1",
            json={"body": "Updated", "is_spoiler": False},
            headers=USER_HEADERS
        ).status_code == 200

    def test_update_comment_permission_denied(self, client, mock_user_data_client):
        mock_user_data_client.update_comment.side_effect = MockRpcError(
            grpc.StatusCode.PERMISSION_DENIED, "not the owner"
        )
        assert client.put(
            "/api/v1/books/the-hobbit/comments/1",
            json={"body": "X", "is_spoiler": False},
            headers=USER_HEADERS
        ).status_code == 403

    def test_update_comment_not_found(self, client, mock_user_data_client):
        mock_user_data_client.update_comment.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert client.put(
            "/api/v1/books/the-hobbit/comments/999",
            json={"body": "X", "is_spoiler": False},
            headers=USER_HEADERS
        ).status_code == 404

    def test_delete_comment_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.delete_comment.return_value = mocker.MagicMock()
        assert client.delete(
            "/api/v1/books/the-hobbit/comments/1", headers=USER_HEADERS
        ).status_code == 204

    def test_delete_comment_requires_auth(self, client, mock_user_data_client):
        assert client.delete("/api/v1/books/the-hobbit/comments/1").status_code == 401

    def test_get_user_comments_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.comments = []
        resp_obj.total_count = 0
        mock_user_data_client.get_user_comments.return_value = resp_obj
        assert client.get("/api/v1/users/me/comments", headers=USER_HEADERS).status_code == 200

    def test_get_user_comments_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/comments").status_code == 401


class TestNoteEndpoints:
    def test_get_book_notes_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.notes = [_note(mocker)]
        resp_obj.total_count = 1
        mock_user_data_client.get_book_notes.return_value = resp_obj
        resp = client.get("/api/v1/books/the-hobbit/notes", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_count"] == 1

    def test_get_book_notes_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/books/the-hobbit/notes").status_code == 401

    def test_create_note_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.note = _note(mocker)
        mock_user_data_client.create_note.return_value = resp_obj
        resp = client.post(
            "/api/v1/books/the-hobbit/notes",
            json={"note_text": "Remember this", "page_number": 42, "is_spoiler": False},
            headers=USER_HEADERS
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["note"]["note_text"] == "Remember this"

    def test_create_note_without_page_number(self, client, mock_user_data_client, mocker):
        n = _note(mocker)
        n.has_page_number = False
        resp_obj = mocker.MagicMock()
        resp_obj.note = n
        mock_user_data_client.create_note.return_value = resp_obj
        resp = client.post(
            "/api/v1/books/the-hobbit/notes",
            json={"note_text": "General note", "is_spoiler": False},
            headers=USER_HEADERS
        )
        assert resp.status_code == 201

    def test_create_note_requires_auth(self, client, mock_user_data_client):
        assert client.post(
            "/api/v1/books/the-hobbit/notes", json={"note_text": "Note"}
        ).status_code == 401

    def test_create_note_empty_text_rejected(self, client, mock_user_data_client):
        assert client.post(
            "/api/v1/books/the-hobbit/notes",
            json={"note_text": ""},
            headers=USER_HEADERS
        ).status_code == 422

    def test_update_note_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.note = _note(mocker)
        mock_user_data_client.update_note.return_value = resp_obj
        assert client.put(
            "/api/v1/books/the-hobbit/notes/1",
            json={"note_text": "Updated", "is_spoiler": False},
            headers=USER_HEADERS
        ).status_code == 200

    def test_update_note_not_found(self, client, mock_user_data_client):
        mock_user_data_client.update_note.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert client.put(
            "/api/v1/books/the-hobbit/notes/999",
            json={"note_text": "X", "is_spoiler": False},
            headers=USER_HEADERS
        ).status_code == 404

    def test_delete_note_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.delete_note.return_value = mocker.MagicMock()
        assert client.delete("/api/v1/books/the-hobbit/notes/1", headers=USER_HEADERS).status_code == 204

    def test_delete_note_requires_auth(self, client, mock_user_data_client):
        assert client.delete("/api/v1/books/the-hobbit/notes/1").status_code == 401

    def test_delete_note_not_found(self, client, mock_user_data_client):
        mock_user_data_client.delete_note.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert client.delete("/api/v1/books/the-hobbit/notes/999", headers=USER_HEADERS).status_code == 404

    def test_get_user_notes_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.notes = []
        resp_obj.total_count = 0
        mock_user_data_client.get_user_notes.return_value = resp_obj
        assert client.get("/api/v1/users/me/notes", headers=USER_HEADERS).status_code == 200

    def test_get_user_notes_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/notes").status_code == 401


class TestPublicBookshelfEndpoints:
    def test_get_public_bookshelves_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.bookshelves = [_bookshelf(mocker)]
        resp_obj.total_count = 1
        mock_user_data_client.get_public_bookshelves.return_value = resp_obj
        resp = client.get("/api/v1/users/alice/bookshelves")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["book_slug"] == "the-hobbit"

    def test_get_public_bookshelves_with_filters(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.bookshelves = []
        resp_obj.total_count = 0
        mock_user_data_client.get_public_bookshelves.return_value = resp_obj
        client.get("/api/v1/users/alice/bookshelves?status=reading&sort_by=book_title&order=asc")
        _, kwargs = mock_user_data_client.get_public_bookshelves.call_args
        assert kwargs["username"] == "alice"
        assert kwargs["status_filter"] == "reading"
        assert kwargs["sort_by"] == "book_title"
        assert kwargs["order"] == "asc"

    def test_get_public_bookshelves_user_not_found(self, client, mock_user_data_client):
        mock_user_data_client.get_public_bookshelves.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "user not found"
        )
        resp = client.get("/api/v1/users/nonexistent_xyz/bookshelves")
        assert resp.status_code == 404
