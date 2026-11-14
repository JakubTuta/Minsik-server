import app.proto.recommendation_pb2 as recommendation_pb2
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


def make_book_item(book_id=1):
    return recommendation_pb2.RecommendationBookItem(
        book_id=book_id,
        work_id=f"OL{book_id}W",
        title=f"Book {book_id}",
        slug=f"book-{book_id}",
        language="en",
        primary_cover_url="https://example.com/cover.jpg",
        author_names=["Author One"],
        author_slugs=["author-one"],
        avg_rating=4.5,
        rating_count=100,
        readers=5000,
        score=9000.0,
    )


def make_author_item(author_id=1):
    return recommendation_pb2.RecommendationAuthorItem(
        author_id=author_id,
        name="Famous Author",
        slug="famous-author",
        photo_url="https://example.com/photo.jpg",
        book_count=10,
        avg_rating=4.2,
        rating_count=50,
        readers=1000,
        score=50000.0,
    )


def make_list_response(item_type="book", key="most_read", title_params=None):
    return recommendation_pb2.RecommendationListResponse(
        key=key,
        display_name="Most Read Books",
        item_type=item_type,
        total=1,
        title_params=title_params or {},
        book_items=[make_book_item()] if item_type == "book" else [],
        author_items=[make_author_item()] if item_type != "book" else [],
    )


class TestGetHomePage:
    def test_success_returns_categories(self, client, mock_recommendation_client, mocker):
        cat = make_list_response(item_type="book", key="most_read")
        mock_recommendation_client.get_home_page.return_value = (
            recommendation_pb2.HomePageResponse(categories=[cat])
        )

        response = client.get("/api/v1/recommendations/home?items_per_category=5")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "sections" in body["data"]
        assert len(body["data"]["sections"]) == 1

    def test_category_structure_for_book_type(self, client, mock_recommendation_client, mocker):
        cat = make_list_response(item_type="book", key="most_read")
        mock_recommendation_client.get_home_page.return_value = (
            recommendation_pb2.HomePageResponse(categories=[cat])
        )

        response = client.get("/api/v1/recommendations/home")

        body = response.json()
        category = body["data"]["sections"][0]
        assert category["item_type"] == "book"
        assert "book_items" in category
        assert category["book_items"][0]["book_id"] == 1

    def test_category_structure_for_author_type(self, client, mock_recommendation_client, mocker):
        cat = make_list_response(item_type="author", key="top_authors")
        mock_recommendation_client.get_home_page.return_value = (
            recommendation_pb2.HomePageResponse(categories=[cat])
        )

        response = client.get("/api/v1/recommendations/home")

        body = response.json()
        category = body["data"]["sections"][0]
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
        mock_recommendation_client.get_available_categories.return_value = (
            recommendation_pb2.AvailableCategoriesResponse(
                categories=[
                    recommendation_pb2.CategoryInfo(
                        key="most_read", display_name="Most Read Books", item_type="book"
                    )
                ]
            )
        )

        response = client.get("/api/v1/recommendations/categories")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        cats = body["data"]["categories"]
        assert len(cats) == 1
        assert cats[0]["key"] == "most_read"
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
        list_resp = make_list_response(item_type="book", key="most_read")
        mock_recommendation_client.get_recommendation_list.return_value = list_resp

        response = client.get("/api/v1/recommendations/most_read?limit=10&offset=0")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["key"] == "most_read"
        assert "book_items" in body["data"]

    def test_passes_limit_and_offset(self, client, mock_recommendation_client, mocker):
        list_resp = make_list_response()
        mock_recommendation_client.get_recommendation_list.return_value = list_resp

        client.get("/api/v1/recommendations/most_read?limit=5&offset=10")

        mock_recommendation_client.get_recommendation_list.assert_called_once_with(
            category="most_read", limit=5, offset=10, language="en", user_id=0
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
        list_resp = make_list_response(item_type="author", key="top_authors")
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

    def test_unauthorized_without_token_returns_401(self, client, mock_recommendation_client):
        response = client.post("/api/v1/admin/recommendations/refresh")

        assert response.status_code == 401

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


class TestSectionShape:
    def test_a_book_section_has_no_author_items_and_nulls_unset_optionals(
        self, client, mock_recommendation_client
    ):
        book = recommendation_pb2.RecommendationBookItem(
            book_id=2**40, title="Dune", slug="dune", avg_rating=4.5
        )
        mock_recommendation_client.get_recommendation_list.return_value = (
            recommendation_pb2.RecommendationListResponse(
                key="most_read", item_type="book", book_items=[book]
            )
        )

        data = client.get("/api/v1/recommendations/most_read").json()["data"]

        assert "author_items" not in data
        item = data["book_items"][0]
        assert item["book_id"] == 2**40
        assert item["avg_rating"] == 4.5
        assert item["work_id"] is None
        assert item["primary_cover_url"] is None

    def test_an_author_section_has_no_book_items(self, client, mock_recommendation_client):
        mock_recommendation_client.get_recommendation_list.return_value = make_list_response(
            item_type="author", key="top_authors"
        )

        data = client.get("/api/v1/recommendations/top_authors").json()["data"]

        assert "book_items" not in data
        assert data["author_items"][0]["photo_url"] == "https://example.com/photo.jpg"
