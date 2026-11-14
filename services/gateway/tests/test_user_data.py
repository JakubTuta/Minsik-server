import asyncio
import datetime
from unittest.mock import AsyncMock

import app.config
import app.grpc_clients
import app.proto.user_data_pb2 as user_data_pb2
import app.routes.user_data
import grpc
import jwt
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


def make_token(user_id: int = 1, role: str = "user") -> str:
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


USER_HEADERS = {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def mock_user_data_client(mocker):
    mock_client = mocker.MagicMock()
    for method in [
        "get_user_book_info",
        "upsert_bookshelf",
        "delete_bookshelf",
        "get_user_bookshelves",
        "get_public_bookshelves",
        "toggle_favourite",
        "get_user_favourites",
        "upsert_rating",
        "delete_rating",
        "get_user_ratings",
        "get_book_comments",
        "create_comment",
        "update_comment",
        "delete_comment",
        "get_user_comments",
    ]:
        setattr(mock_client, method, mocker.AsyncMock())
    mocker.patch.object(app.grpc_clients, "user_data_client", mock_client)
    return mock_client


def _bookshelf():
    return user_data_pb2.Bookshelf(
        bookshelf_id=1,
        user_id=1,
        book_id=100,
        book_slug="the-hobbit",
        book_title="The Hobbit",
        status="reading",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def _rating():
    return user_data_pb2.Rating(
        rating_id=1,
        user_id=1,
        book_id=100,
        book_slug="the-hobbit",
        book_title="The Hobbit",
        overall_rating=4.5,
        review_text="Great book",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        book_avg_rating=4.2,
        book_rating_count=100,
    )


def _comment():
    return user_data_pb2.Comment(
        comment_id=1,
        user_id=1,
        username="testuser",
        book_id=100,
        book_slug="the-hobbit",
        body="Loved it!",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        book_title="The Hobbit",
    )


def _comment_with_rating():
    return user_data_pb2.BookCommentWithRating(
        comment_id=1,
        user_id=1,
        username="testuser",
        book_id=100,
        book_slug="the-hobbit",
        body="Loved it!",
        comment_created_at="2026-01-01T00:00:00",
        comment_updated_at="2026-01-01T00:00:00",
    )


class TestUserBookInfoEndpoint:
    def test_all_data_present(self, client, mock_user_data_client, mocker):
        mock_user_data_client.get_user_book_info.return_value = (
            user_data_pb2.UserBookInfoResponse(
                bookshelf=_bookshelf(), rating=_rating(), comment=_comment()
            )
        )
        resp = client.get("/api/v1/users/me/books/the-hobbit", headers=USER_HEADERS)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bookshelf"] is not None
        assert data["bookshelf"]["status"] == "reading"
        assert data["rating"] is not None
        assert data["rating"]["overall_rating"] == 4.5
        assert data["comment"] is not None
        assert data["comment"]["body"] == "Loved it!"
        assert data["comment"]["username"] == "testuser"

    def test_all_data_absent(self, client, mock_user_data_client, mocker):
        mock_user_data_client.get_user_book_info.return_value = (
            user_data_pb2.UserBookInfoResponse()
        )
        resp = client.get("/api/v1/users/me/books/the-hobbit", headers=USER_HEADERS)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bookshelf"] is None
        assert data["rating"] is None
        assert data["comment"] is None

    def test_partial_data(self, client, mock_user_data_client, mocker):
        mock_user_data_client.get_user_book_info.return_value = (
            user_data_pb2.UserBookInfoResponse(bookshelf=_bookshelf())
        )
        resp = client.get("/api/v1/users/me/books/the-hobbit", headers=USER_HEADERS)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bookshelf"] is not None
        assert data["rating"] is None
        assert data["comment"] is None

    def test_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/books/the-hobbit").status_code == 401

    def test_book_not_found(self, client, mock_user_data_client):
        mock_user_data_client.get_user_book_info.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "book not found"
        )
        resp = client.get("/api/v1/users/me/books/nonexistent", headers=USER_HEADERS)
        assert resp.status_code == 404


class TestBookshelfEndpoints:
    def test_upsert_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.upsert_bookshelf.return_value = (
            user_data_pb2.BookshelfResponse(bookshelf=_bookshelf())
        )
        resp = client.put(
            "/api/v1/users/me/bookshelves/the-hobbit",
            json={"status": "reading"},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["bookshelf"]["status"] == "reading"

    def test_upsert_requires_auth(self, client, mock_user_data_client):
        resp = client.put(
            "/api/v1/users/me/bookshelves/the-hobbit", json={"status": "reading"}
        )
        assert resp.status_code == 401

    def test_upsert_invalid_status_rejected(self, client, mock_user_data_client):
        resp = client.put(
            "/api/v1/users/me/bookshelves/the-hobbit",
            json={"status": "bad_value"},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 422

    def test_upsert_book_not_found(self, client, mock_user_data_client):
        mock_user_data_client.upsert_bookshelf.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "book not found"
        )
        resp = client.put(
            "/api/v1/users/me/bookshelves/unknown",
            json={"status": "reading"},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 404

    def test_get_bookshelves_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.get_user_bookshelves.return_value = (
            user_data_pb2.BookshelvesListResponse(
                bookshelves=[_bookshelf()], total_count=1
            )
        )
        resp = client.get("/api/v1/users/me/bookshelves", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_count"] == 1
        assert len(resp.json()["data"]["items"]) == 1

    def test_get_bookshelves_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/bookshelves").status_code == 401

    def test_get_bookshelves_status_filter_forwarded(
        self, client, mock_user_data_client, mocker
    ):
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
        assert (
            client.get("/api/v1/users/me/bookshelves", headers=USER_HEADERS).status_code
            == 500
        )

    def test_delete_bookshelf_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.delete_bookshelf.return_value = mocker.MagicMock()
        assert (
            client.delete(
                "/api/v1/users/me/bookshelves/the-hobbit", headers=USER_HEADERS
            ).status_code
            == 204
        )

    def test_delete_bookshelf_requires_auth(self, client, mock_user_data_client):
        assert (
            client.delete("/api/v1/users/me/bookshelves/the-hobbit").status_code == 401
        )

    def test_delete_bookshelf_not_found(self, client, mock_user_data_client):
        mock_user_data_client.delete_bookshelf.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert (
            client.delete(
                "/api/v1/users/me/bookshelves/unknown", headers=USER_HEADERS
            ).status_code
            == 404
        )


class TestFavouriteEndpoints:
    def test_add_favourite_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.toggle_favourite.return_value = (
            user_data_pb2.FavouriteResponse(
                is_favorite=True, book_id=100, book_slug="the-hobbit"
            )
        )
        resp = client.post("/api/v1/books/the-hobbit/favourite", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_favorite"] is True
        _, kwargs = mock_user_data_client.toggle_favourite.call_args
        assert kwargs["is_favorite"] is True

    def test_remove_favourite_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.toggle_favourite.return_value = (
            user_data_pb2.FavouriteResponse(
                is_favorite=False, book_id=100, book_slug="the-hobbit"
            )
        )
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
        assert (
            client.post(
                "/api/v1/books/unknown/favourite", headers=USER_HEADERS
            ).status_code
            == 404
        )

    def test_get_favourites_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.bookshelves = []
        resp_obj.total_count = 0
        mock_user_data_client.get_user_favourites.return_value = resp_obj
        assert (
            client.get("/api/v1/users/me/favourites", headers=USER_HEADERS).status_code
            == 200
        )

    def test_get_favourites_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/favourites").status_code == 401


class TestRatingEndpoints:
    def test_upsert_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.upsert_rating.return_value = (
            user_data_pb2.RatingResponse(rating=_rating())
        )
        resp = client.post(
            "/api/v1/books/the-hobbit/rate",
            json={"overall_rating": 4.5, "review_text": "Great!"},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["rating"]["overall_rating"] == 4.5

    def test_upsert_requires_auth(self, client, mock_user_data_client):
        assert (
            client.post(
                "/api/v1/books/the-hobbit/rate", json={"overall_rating": 4.0}
            ).status_code
            == 401
        )

    def test_upsert_missing_overall_rating_rejected(
        self, client, mock_user_data_client
    ):
        assert (
            client.post(
                "/api/v1/books/the-hobbit/rate", json={}, headers=USER_HEADERS
            ).status_code
            == 422
        )

    def test_upsert_out_of_range_rejected(self, client, mock_user_data_client):
        assert (
            client.post(
                "/api/v1/books/the-hobbit/rate",
                json={"overall_rating": 6.0},
                headers=USER_HEADERS,
            ).status_code
            == 422
        )

    def test_upsert_below_range_rejected(self, client, mock_user_data_client):
        assert (
            client.post(
                "/api/v1/books/the-hobbit/rate",
                json={"overall_rating": 0.4},
                headers=USER_HEADERS,
            ).status_code
            == 422
        )

    def test_upsert_book_not_found(self, client, mock_user_data_client):
        mock_user_data_client.upsert_rating.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert (
            client.post(
                "/api/v1/books/unknown/rate",
                json={"overall_rating": 4.0},
                headers=USER_HEADERS,
            ).status_code
            == 404
        )

    def test_delete_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.delete_rating.return_value = mocker.MagicMock()
        assert (
            client.delete(
                "/api/v1/books/the-hobbit/rate", headers=USER_HEADERS
            ).status_code
            == 204
        )

    def test_delete_requires_auth(self, client, mock_user_data_client):
        assert client.delete("/api/v1/books/the-hobbit/rate").status_code == 401

    def test_delete_not_found(self, client, mock_user_data_client):
        mock_user_data_client.delete_rating.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert (
            client.delete(
                "/api/v1/books/the-hobbit/rate", headers=USER_HEADERS
            ).status_code
            == 404
        )

    def test_get_ratings_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.get_user_ratings.return_value = (
            user_data_pb2.RatingsListResponse(ratings=[_rating()], total_count=1)
        )
        resp = client.get("/api/v1/users/me/ratings", headers=USER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_count"] == 1

    def test_get_ratings_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/ratings").status_code == 401


class TestCommentEndpoints:
    def test_get_book_comments_is_public(self, client, mock_user_data_client, mocker):
        mock_user_data_client.get_book_comments.return_value = (
            user_data_pb2.BookCommentsResponse(
                comments=[_comment_with_rating()], total_count=1
            )
        )
        resp = client.get("/api/v1/books/the-hobbit/comments")
        assert resp.status_code == 200
        assert resp.json()["data"]["total_count"] == 1

    def test_get_book_comments_no_auth_needed(
        self, client, mock_user_data_client, mocker
    ):
        mock_user_data_client.get_book_comments.return_value = (
            user_data_pb2.BookCommentsResponse()
        )
        assert client.get("/api/v1/books/the-hobbit/comments").status_code == 200

    def test_get_book_comments_include_spoilers_forwarded(
        self, client, mock_user_data_client, mocker
    ):
        resp_obj = mocker.MagicMock()
        resp_obj.comments = []
        resp_obj.total_count = 0
        resp_obj.HasField = lambda f: False
        mock_user_data_client.get_book_comments.return_value = resp_obj
        client.get("/api/v1/books/the-hobbit/comments?include_spoilers=true")
        _, kwargs = mock_user_data_client.get_book_comments.call_args
        assert kwargs["include_spoilers"] is True

    def test_create_comment_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.create_comment.return_value = (
            user_data_pb2.CommentResponse(comment=_comment())
        )
        resp = client.post(
            "/api/v1/books/the-hobbit/comments",
            json={"body": "Loved it!", "is_spoiler": False},
            headers=USER_HEADERS,
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["comment"]["body"] == "Loved it!"
        assert resp.json()["data"]["comment"]["username"] == "testuser"

    def test_create_comment_requires_auth(self, client, mock_user_data_client):
        assert (
            client.post(
                "/api/v1/books/the-hobbit/comments", json={"body": "Hi"}
            ).status_code
            == 401
        )

    def test_create_comment_empty_body_rejected(self, client, mock_user_data_client):
        assert (
            client.post(
                "/api/v1/books/the-hobbit/comments",
                json={"body": ""},
                headers=USER_HEADERS,
            ).status_code
            == 422
        )

    def test_update_comment_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.update_comment.return_value = (
            user_data_pb2.CommentResponse(comment=_comment())
        )
        assert (
            client.put(
                "/api/v1/books/the-hobbit/comments/1",
                json={"body": "Updated", "is_spoiler": False},
                headers=USER_HEADERS,
            ).status_code
            == 200
        )

    def test_update_comment_permission_denied(self, client, mock_user_data_client):
        mock_user_data_client.update_comment.side_effect = MockRpcError(
            grpc.StatusCode.PERMISSION_DENIED, "not the owner"
        )
        assert (
            client.put(
                "/api/v1/books/the-hobbit/comments/1",
                json={"body": "X", "is_spoiler": False},
                headers=USER_HEADERS,
            ).status_code
            == 403
        )

    def test_update_comment_not_found(self, client, mock_user_data_client):
        mock_user_data_client.update_comment.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "not found"
        )
        assert (
            client.put(
                "/api/v1/books/the-hobbit/comments/999",
                json={"body": "X", "is_spoiler": False},
                headers=USER_HEADERS,
            ).status_code
            == 404
        )

    def test_delete_comment_success(self, client, mock_user_data_client, mocker):
        mock_user_data_client.delete_comment.return_value = mocker.MagicMock()
        assert (
            client.delete(
                "/api/v1/books/the-hobbit/comments/1", headers=USER_HEADERS
            ).status_code
            == 204
        )

    def test_delete_comment_requires_auth(self, client, mock_user_data_client):
        assert client.delete("/api/v1/books/the-hobbit/comments/1").status_code == 401

    def test_get_user_comments_success(self, client, mock_user_data_client, mocker):
        resp_obj = mocker.MagicMock()
        resp_obj.comments = []
        resp_obj.total_count = 0
        mock_user_data_client.get_user_comments.return_value = resp_obj
        assert (
            client.get("/api/v1/users/me/comments", headers=USER_HEADERS).status_code
            == 200
        )

    def test_get_user_comments_requires_auth(self, client, mock_user_data_client):
        assert client.get("/api/v1/users/me/comments").status_code == 401


class TestPublicBookshelfEndpoints:
    def test_get_public_bookshelves_success(
        self, client, mock_user_data_client, mocker
    ):
        mock_user_data_client.get_public_bookshelves.return_value = (
            user_data_pb2.BookshelvesListResponse(
                bookshelves=[_bookshelf()], total_count=1
            )
        )
        resp = client.get("/api/v1/users/alice/bookshelves")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["book_slug"] == "the-hobbit"

    def test_get_public_bookshelves_with_filters(
        self, client, mock_user_data_client, mocker
    ):
        resp_obj = mocker.MagicMock()
        resp_obj.bookshelves = []
        resp_obj.total_count = 0
        mock_user_data_client.get_public_bookshelves.return_value = resp_obj
        client.get(
            "/api/v1/users/alice/bookshelves?status=reading&sort_by=book_title&order=asc"
        )
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


class TestPersonalRefreshAfterWrite:
    @pytest.fixture(autouse=True)
    def _enabled(self, monkeypatch):
        monkeypatch.setattr(
            app.config.settings, "recommendation_recompute_on_user_write", True
        )
        app.routes.user_data._personal_refresh_state.clear()

    async def test_refresh_uses_the_readers_language(self, monkeypatch):
        refresh = AsyncMock()
        monkeypatch.setattr(
            app.grpc_clients.recommendation_client, "refresh_personal_home", refresh
        )

        await app.routes.user_data._refresh_personal_recommendations_after_user_write(
            7, "pl"
        )

        refresh.assert_awaited_once_with(user_id=7, language="pl")

    async def test_writes_during_a_refresh_collapse_into_one_trailing_run(
        self, monkeypatch
    ):
        started = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def slow_refresh(user_id: int, language: str):
            calls.append((user_id, language))
            started.set()
            await release.wait()

        monkeypatch.setattr(
            app.grpc_clients.recommendation_client,
            "refresh_personal_home",
            slow_refresh,
        )
        refresh = app.routes.user_data._refresh_personal_recommendations_after_user_write

        first = asyncio.create_task(refresh(7, "en"))
        await started.wait()
        for _ in range(5):
            await refresh(7, "en")
        release.set()
        await first

        assert calls == [(7, "en"), (7, "en")]
        assert app.routes.user_data._personal_refresh_state == {}

    async def test_a_failed_refresh_does_not_block_the_next_one(self, monkeypatch):
        refresh = AsyncMock(side_effect=[RuntimeError("boom"), None])
        monkeypatch.setattr(
            app.grpc_clients.recommendation_client, "refresh_personal_home", refresh
        )
        run = app.routes.user_data._refresh_personal_recommendations_after_user_write

        await run(7, "en")
        await run(7, "en")

        assert refresh.await_count == 2


class TestUserDataMapping:
    def test_unset_sub_ratings_and_series_are_null_and_set_ones_are_kept(
        self, client, mock_user_data_client
    ):
        rating = _rating()
        rating.pacing = 0.0
        rating.book_series_name = "The Hobbit Series"
        mock_user_data_client.upsert_rating.return_value = user_data_pb2.RatingResponse(
            rating=rating
        )

        resp = client.post(
            "/api/v1/books/the-hobbit/rate",
            json={"overall_rating": 4.5},
            headers=USER_HEADERS,
        )

        data = resp.json()["data"]["rating"]
        assert data["pacing"] == 0.0
        assert data["humor"] is None
        assert data["book_series_name"] == "The Hobbit Series"
        assert data["book_series_slug"] is None

    def test_a_comment_without_a_rating_has_a_null_rating(
        self, client, mock_user_data_client
    ):
        mock_user_data_client.get_book_comments.return_value = (
            user_data_pb2.BookCommentsResponse(
                comments=[_comment_with_rating()], total_count=1
            )
        )

        resp = client.get("/api/v1/books/the-hobbit/comments")

        data = resp.json()["data"]
        assert data["items"][0]["rating"] is None
        assert data["my_entry"] is None

    def test_a_rated_comment_nests_its_scores(self, client, mock_user_data_client):
        rated = _comment_with_rating()
        rated.rating.overall_rating = 4.5
        rated.rating.humor = 3.0
        mock_user_data_client.get_book_comments.return_value = (
            user_data_pb2.BookCommentsResponse(
                comments=[rated], my_entry=rated, total_count=1
            )
        )

        resp = client.get("/api/v1/books/the-hobbit/comments")

        data = resp.json()["data"]
        assert data["items"][0]["rating"]["overall_rating"] == 4.5
        assert data["items"][0]["rating"]["humor"] == 3.0
        assert data["items"][0]["rating"]["pacing"] is None
        assert data["items"][0]["rating"]["review_text"] is None
        assert data["my_entry"]["rating"]["humor"] == 3.0

    def test_profile_stats_carry_the_rating_distribution_as_an_object(
        self, client, mock_user_data_client, mocker
    ):
        mock_user_data_client.get_public_profile_stats = mocker.AsyncMock(
            return_value=user_data_pb2.ProfileStatsResponse(
                stats=user_data_pb2.ProfileStats(
                    read_count=3, rating_distribution={"4.5": 2}, average_rating=4.5
                )
            )
        )

        resp = client.get("/api/v1/users/alice/stats")

        stats = resp.json()["data"]["stats"]
        assert stats["rating_distribution"] == {"4.5": 2}
        assert stats["read_count"] == 3

    def test_profile_overview_reading_now_is_null_until_set(
        self, client, mock_user_data_client, mocker
    ):
        mock_user_data_client.get_profile_overview = mocker.AsyncMock(
            return_value=user_data_pb2.ProfileOverviewResponse(
                user=user_data_pb2.PublicUser(user_id=2**40, username="alice")
            )
        )

        resp = client.get("/api/v1/users/alice/profile-overview")

        data = resp.json()["data"]
        assert data["reading_now"] is None
        assert data["user"]["user_id"] == 2**40

    def test_year_in_review_marks_absent_books_and_ratings_as_null(
        self, client, mock_user_data_client, mocker
    ):
        review = user_data_pb2.YearInReview(year=2026)
        review.longest_book.CopyFrom(
            user_data_pb2.YearBook(book_slug="dune", number_of_pages=600)
        )
        review.rating_distribution["5.0"] = 1
        mock_user_data_client.get_year_in_review = mocker.AsyncMock(
            return_value=user_data_pb2.YearInReviewResponse(review=review)
        )

        resp = client.get("/api/v1/users/me/year-in-review", headers=USER_HEADERS)

        data = resp.json()["data"]["review"]
        assert data["shortest_book"] is None
        assert data["longest_book"]["book_slug"] == "dune"
        assert data["longest_book"]["my_rating"] is None
        assert data["rating_distribution"] == {"5.0": 1}
