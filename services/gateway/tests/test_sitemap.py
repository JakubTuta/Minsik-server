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


def make_slug_item(mocker, slug="the-hobbit", updated_at="2026-01-01T00:00:00", language="en"):
    item = mocker.MagicMock()
    item.slug = slug
    item.updated_at = updated_at
    # Every field the route reads must be set explicitly: an unset attribute on
    # a MagicMock returns another MagicMock, which is truthy and then fails to
    # serialize, surfacing as an opaque 500 rather than a missing-field error.
    item.language = language
    return item


def make_slugs_response(mocker, slugs=None, total_count=2):
    resp = mocker.MagicMock()
    resp.items = [make_slug_item(mocker, slug=s) for s in (slugs or ["the-hobbit", "dune"])]
    resp.total_count = total_count
    return resp


class TestListSitemapSlugs:
    def test_success_returns_items_and_total(self, client, mock_books_client, mocker):
        mock_books_client.list_sitemap_slugs.return_value = make_slugs_response(mocker)

        response = client.get("/api/v1/sitemap/slugs?entity=books&limit=100&offset=0")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["total_count"] == 2
        assert body["data"]["items"][0]["slug"] == "the-hobbit"
        mock_books_client.list_sitemap_slugs.assert_awaited_once_with(
            entity="books", limit=100, offset=0
        )

    def test_defaults_applied(self, client, mock_books_client, mocker):
        mock_books_client.list_sitemap_slugs.return_value = make_slugs_response(mocker)

        response = client.get("/api/v1/sitemap/slugs")

        assert response.status_code == 200
        mock_books_client.list_sitemap_slugs.assert_awaited_once_with(
            entity="books", limit=1000, offset=0
        )

    def test_empty_updated_at_becomes_null(self, client, mock_books_client, mocker):
        resp = mocker.MagicMock()
        item = make_slug_item(mocker, slug="no-date", updated_at="")
        resp.items = [item]
        resp.total_count = 1
        mock_books_client.list_sitemap_slugs.return_value = resp

        response = client.get("/api/v1/sitemap/slugs?entity=series")

        assert response.status_code == 200
        assert response.json()["data"]["items"][0]["updated_at"] is None

    def test_invalid_entity_rejected(self, client, mock_books_client):
        response = client.get("/api/v1/sitemap/slugs?entity=users")

        assert response.status_code == 422
        mock_books_client.list_sitemap_slugs.assert_not_called()

    def test_limit_above_max_rejected(self, client, mock_books_client):
        response = client.get("/api/v1/sitemap/slugs?entity=books&limit=20000")

        assert response.status_code == 422
        mock_books_client.list_sitemap_slugs.assert_not_called()

    def test_grpc_error_returns_500(self, client, mock_books_client):
        mock_books_client.list_sitemap_slugs.side_effect = MockRpcError(
            grpc.StatusCode.INTERNAL, "boom"
        )

        response = client.get("/api/v1/sitemap/slugs?entity=authors")

        assert response.status_code == 500
