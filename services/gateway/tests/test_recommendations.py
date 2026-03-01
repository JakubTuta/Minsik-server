import pytest
import grpc


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details=""):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


def make_book_item(mocker, book_id=1):
    item = mocker.MagicMock()
    item.book_id = book_id
    item.title = f"Book {book_id}"
    item.slug = f"book-{book_id}"
    item.language = "en"
    item.primary_cover_url = "https://example.com/cover.jpg"
    item.author_names = ["Author One"]
    item.author_slugs = ["author-one"]
    item.avg_rating = "4.50"
    item.rating_count = 100
    item.score = 9000.0
    return item


def make_author_item(mocker, author_id=1):
    item = mocker.MagicMock()
    item.author_id = author_id
    item.name = "Famous Author"
    item.slug = "famous-author"
    item.photo_url = "https://example.com/photo.jpg"
    item.book_count = 10
    item.score = 50000.0
    return item


def make_list_response(mocker, item_type="book", category="most_read"):
    resp = mocker.MagicMock()
    resp.category = category
    resp.display_name = "Most Read Books"
    resp.item_type = item_type
    resp.total = 1
    if item_type == "book":
        resp.book_items = [make_book_item(mocker)]
        resp.author_items = []
    else:
        resp.author_items = [make_author_item(mocker)]
        resp.book_items = []
    return resp


class TestGetHomePage:
    def test_success_returns_categories(self, client, mock_recommendation_client, mocker):
        cat = make_list_response(mocker, item_type="book", category="most_read")
        home_response = mocker.MagicMock()
        home_response.categories = [cat]
        mock_recommendation_client.get_home_page.return_value = home_response

        response = client.get("/api/v1/recommendations/home?items_per_category=5")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "categories" in body["data"]
        assert len(body["data"]["categories"]) == 1

    def test_category_structure_for_book_type(self, client, mock_recommendation_client, mocker):
        cat = make_list_response(mocker, item_type="book", category="most_read")
        home_response = mocker.MagicMock()
        home_response.categories = [cat]
        mock_recommendation_client.get_home_page.return_value = home_response

        response = client.get("/api/v1/recommendations/home")

        body = response.json()
        category = body["data"]["categories"][0]
        assert category["item_type"] == "book"
        assert "book_items" in category
        assert category["book_items"][0]["book_id"] == 1

    def test_category_structure_for_author_type(self, client, mock_recommendation_client, mocker):
        cat = make_list_response(mocker, item_type="author", category="top_authors")
        home_response = mocker.MagicMock()
        home_response.categories = [cat]
        mock_recommendation_client.get_home_page.return_value = home_response

        response = client.get("/api/v1/recommendations/home")

        body = response.json()
        category = body["data"]["categories"][0]
        assert category["item_type"] == "author"
        assert "author_items" in category
        assert category["author_items"][0]["author_id"] == 1

    def test_unavailable_returns_503(self, client, mock_recommendation_client):
        mock_recommendation_client.get_home_page.side_effect = MockRpcError(grpc.StatusCode.UNAVAILABLE)

        response = client.get("/api/v1/recommendations/home")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "UNAVAILABLE"

    def test_grpc_internal_error_returns_500(self, client, mock_recommendation_client):
        mock_recommendation_client.get_home_page.side_effect = MockRpcError(grpc.StatusCode.INTERNAL)

        response = client.get("/api/v1/recommendations/home")

        assert response.status_code == 500

    def test_unexpected_error_returns_500(self, client, mock_recommendation_client):
        mock_recommendation_client.get_home_page.side_effect = RuntimeError("unexpected")

        response = client.get("/api/v1/recommendations/home")

        assert response.status_code == 500


class TestGetAvailableCategories:
    def test_success_returns_category_list(self, client, mock_recommendation_client, mocker):
        cat_info = mocker.MagicMock()
        cat_info.category = "most_read"
        cat_info.display_name = "Most Read Books"
        cat_info.item_type = "book"

        avail_response = mocker.MagicMock()
        avail_response.categories = [cat_info]
        mock_recommendation_client.get_available_categories.return_value = avail_response

        response = client.get("/api/v1/recommendations/categories")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        cats = body["data"]["categories"]
        assert len(cats) == 1
        assert cats[0]["category"] == "most_read"
        assert cats[0]["display_name"] == "Most Read Books"
        assert cats[0]["item_type"] == "book"

    def test_grpc_error_returns_500(self, client, mock_recommendation_client):
        mock_recommendation_client.get_available_categories.side_effect = MockRpcError(grpc.StatusCode.INTERNAL)

        response = client.get("/api/v1/recommendations/categories")

        assert response.status_code == 500

    def test_unexpected_error_returns_500(self, client, mock_recommendation_client):
        mock_recommendation_client.get_available_categories.side_effect = RuntimeError("unexpected")

        response = client.get("/api/v1/recommendations/categories")

        assert response.status_code == 500


class TestGetRecommendationList:
    def test_success_returns_list(self, client, mock_recommendation_client, mocker):
        list_resp = make_list_response(mocker, item_type="book", category="most_read")
        mock_recommendation_client.get_recommendation_list.return_value = list_resp

        response = client.get("/api/v1/recommendations/most_read?limit=10&offset=0")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["category"] == "most_read"
        assert "book_items" in body["data"]

    def test_passes_limit_and_offset(self, client, mock_recommendation_client, mocker):
        list_resp = make_list_response(mocker)
        mock_recommendation_client.get_recommendation_list.return_value = list_resp

        client.get("/api/v1/recommendations/most_read?limit=5&offset=10")

        mock_recommendation_client.get_recommendation_list.assert_called_once_with(
            category="most_read", limit=5, offset=10
        )

    def test_not_found_returns_404(self, client, mock_recommendation_client):
        mock_recommendation_client.get_recommendation_list.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "Category not found"
        )

        response = client.get("/api/v1/recommendations/nonexistent")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_unavailable_returns_503(self, client, mock_recommendation_client):
        mock_recommendation_client.get_recommendation_list.side_effect = MockRpcError(grpc.StatusCode.UNAVAILABLE)

        response = client.get("/api/v1/recommendations/most_read")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "UNAVAILABLE"

    def test_grpc_internal_error_returns_500(self, client, mock_recommendation_client):
        mock_recommendation_client.get_recommendation_list.side_effect = MockRpcError(grpc.StatusCode.INTERNAL)

        response = client.get("/api/v1/recommendations/most_read")

        assert response.status_code == 500

    def test_unexpected_error_returns_500(self, client, mock_recommendation_client):
        mock_recommendation_client.get_recommendation_list.side_effect = RuntimeError("unexpected")

        response = client.get("/api/v1/recommendations/most_read")

        assert response.status_code == 500

    def test_author_category_returns_author_items(self, client, mock_recommendation_client, mocker):
        list_resp = make_list_response(mocker, item_type="author", category="top_authors")
        mock_recommendation_client.get_recommendation_list.return_value = list_resp

        response = client.get("/api/v1/recommendations/top_authors")

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["item_type"] == "author"
        assert "author_items" in body["data"]


class TestAdminRefreshRecommendations:
    def test_success_returns_ok(self, client, mock_recommendation_client, mocker):
        refresh_response = mocker.MagicMock()
        refresh_response.success = True
        refresh_response.message = "Refreshed successfully"
        mock_recommendation_client.refresh_recommendations.return_value = refresh_response

        admin_token = _make_admin_token()
        response = client.post(
            "/api/v1/admin/recommendations/refresh",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["success"] is True

    def test_unauthorized_without_token_returns_403(self, client, mock_recommendation_client):
        response = client.post("/api/v1/admin/recommendations/refresh")

        assert response.status_code == 403

    def test_unauthorized_for_non_admin_returns_403(self, client, mock_recommendation_client):
        user_token = _make_user_token()
        response = client.post(
            "/api/v1/admin/recommendations/refresh",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 403

    def test_grpc_error_returns_500(self, client, mock_recommendation_client):
        mock_recommendation_client.refresh_recommendations.side_effect = MockRpcError(grpc.StatusCode.INTERNAL)

        admin_token = _make_admin_token()
        response = client.post(
            "/api/v1/admin/recommendations/refresh",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 500

    def test_unexpected_error_returns_500(self, client, mock_recommendation_client):
        mock_recommendation_client.refresh_recommendations.side_effect = RuntimeError("unexpected")

        admin_token = _make_admin_token()
        response = client.post(
            "/api/v1/admin/recommendations/refresh",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 500


def _make_admin_token() -> str:
    import datetime
    import jwt
    import app.config

    payload = {
        "sub": "1",
        "role": "admin",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15),
    }
    return jwt.encode(payload, app.config.settings.jwt_secret_key, algorithm=app.config.settings.jwt_algorithm)


def _make_user_token() -> str:
    import datetime
    import jwt
    import app.config

    payload = {
        "sub": "2",
        "role": "user",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15),
    }
    return jwt.encode(payload, app.config.settings.jwt_secret_key, algorithm=app.config.settings.jwt_algorithm)
