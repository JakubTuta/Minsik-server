import app.grpc_clients
import app.proto.books_pb2
import grpc
import pytest


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details=""):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


@pytest.fixture
def mock_user_data_client(mocker):
    mock_client = mocker.MagicMock()
    mock_client.get_book_comments = mocker.AsyncMock()
    mocker.patch.object(app.grpc_clients, "user_data_client", mock_client)
    return mock_client


def make_book_summary(book_id=1, first_sentence=""):
    return app.proto.books_pb2.BookSummary(
        book_id=book_id,
        work_id=f"OL{book_id}W",
        language="en",
        title=f"Book {book_id}",
        slug=f"book-{book_id}",
        original_publication_year=1949,
        primary_cover_url="https://example.com/cover.jpg",
        rating_count=10,
        avg_rating=4.5,
        ol_rating_count=5,
        ol_avg_rating=4.0,
        rarity="rare",
        first_sentence=first_sentence,
    )


class TestBookCommentsRatingFilter:
    def test_repeated_rating_filter_is_accepted(
        self, client, mock_user_data_client, mocker
    ):
        # A numeric bound declared on the Query itself is applied to the list,
        # which raised TypeError inside dependency resolution and answered 500
        # for every request that used the filter.
        response_obj = mocker.MagicMock()
        response_obj.comments = []
        response_obj.total_count = 0
        response_obj.HasField.return_value = False
        mock_user_data_client.get_book_comments.return_value = response_obj

        response = client.get(
            "/api/v1/books/the-hobbit/comments?rating_filter=4.5&rating_filter=5.0"
        )

        assert response.status_code == 200
        kwargs = mock_user_data_client.get_book_comments.await_args.kwargs
        assert kwargs["rating_filters"] == [4.5, 5.0]

    def test_out_of_range_rating_filter_is_rejected(
        self, client, mock_user_data_client
    ):
        response = client.get("/api/v1/books/the-hobbit/comments?rating_filter=9")

        assert response.status_code == 422

    def test_omitted_rating_filter_sends_an_empty_list(
        self, client, mock_user_data_client, mocker
    ):
        response_obj = mocker.MagicMock()
        response_obj.comments = []
        response_obj.total_count = 0
        response_obj.HasField.return_value = False
        mock_user_data_client.get_book_comments.return_value = response_obj

        response = client.get("/api/v1/books/the-hobbit/comments")

        assert response.status_code == 200
        assert mock_user_data_client.get_book_comments.await_args.kwargs[
            "rating_filters"
        ] == []


class TestGameEndpointErrorEnvelope:
    @pytest.mark.parametrize(
        "path,method_name",
        [
            ("/api/v1/case/open", "open_case"),
            ("/api/v1/pack/open", "open_pack"),
            ("/api/v1/slots/spin", "spin_slots"),
        ],
    )
    def test_no_eligible_books_uses_a_coded_envelope(
        self, client, mock_books_client, mocker, path, method_name
    ):
        # The frontend translates by error code; a bare `detail` string reaches
        # the reader as untranslated English.
        setattr(
            mock_books_client,
            method_name,
            mocker.AsyncMock(
                side_effect=MockRpcError(grpc.StatusCode.NOT_FOUND, "none")
            ),
        )

        response = client.get(path)

        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NO_ELIGIBLE_BOOKS"


class TestDiscover:
    def test_no_match_is_a_404_with_a_code(self, client, mock_books_client, mocker):
        mock_books_client.discover_book = mocker.AsyncMock(
            side_effect=MockRpcError(grpc.StatusCode.NOT_FOUND, "none")
        )

        response = client.post("/api/v1/discover", json={})

        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NO_MATCHING_BOOKS"


class TestAuthorQuote:
    def test_reads_the_sentence_off_the_summary(
        self, client, mock_books_client, mocker
    ):
        # One call, not one per candidate book: the summaries already carry it.
        books_response = mocker.MagicMock()
        books_response.books = [
            make_book_summary(1),
            make_book_summary(2, first_sentence="It was a bright cold day."),
        ]
        mock_books_client.get_author_books = mocker.AsyncMock(
            return_value=books_response
        )
        mock_books_client.get_book = mocker.AsyncMock()

        response = client.get("/api/v1/authors/george-orwell/quote")

        assert response.status_code == 200
        assert response.json()["data"]["first_sentence"] == "It was a bright cold day."
        assert response.json()["data"]["book_slug"] == "book-2"
        mock_books_client.get_book.assert_not_awaited()

    def test_no_sentence_anywhere_returns_null_data(
        self, client, mock_books_client, mocker
    ):
        books_response = mocker.MagicMock()
        books_response.books = [make_book_summary(1)]
        mock_books_client.get_author_books = mocker.AsyncMock(
            return_value=books_response
        )

        response = client.get("/api/v1/authors/george-orwell/quote")

        assert response.status_code == 200
        assert response.json()["data"] is None


class TestBookSummaryMapping:
    def test_unset_optionals_are_null_and_ratings_are_numbers(
        self, client, mock_books_client, mocker
    ):
        mock_books_client.get_author_books = mocker.AsyncMock(
            return_value=app.proto.books_pb2.BooksListResponse(
                books=[make_book_summary(2**40)], total_count=1
            )
        )

        response = client.get("/api/v1/authors/george-orwell/books")

        book = response.json()["data"]["books"][0]
        assert book["book_id"] == 2**40
        assert book["avg_rating"] == 4.5
        assert book["ol_avg_rating"] == 4.0
        assert book["series"] is None
        assert book["series_position"] is None
        assert book["description"] is None
        assert book["number_of_pages"] is None

    def test_a_series_volume_carries_its_position_and_series(
        self, client, mock_books_client, mocker
    ):
        volume = make_book_summary(3)
        volume.series_position = 0.0
        volume.series.CopyFrom(
            app.proto.books_pb2.SeriesInfo(series_id=9, name="Dune", slug="dune")
        )
        mock_books_client.get_series_books = mocker.AsyncMock(
            return_value=app.proto.books_pb2.BooksListResponse(
                books=[volume], total_count=1
            )
        )

        response = client.get("/api/v1/series/dune/books")

        book = response.json()["data"]["books"][0]
        assert book["series_position"] == 0.0
        assert book["series"] == {
            "series_id": 9,
            "name": "Dune",
            "slug": "dune",
            "total_books": None,
        }


class TestBookDetailMapping:
    def test_optional_text_is_null_until_set(self, client, mock_books_client, mocker):
        detail = app.proto.books_pb2.BookDetail(
            book_id=1,
            title="Dune",
            slug="dune",
            language="en",
            avg_rating=4.25,
            created_at="2020-01-01",
            updated_at="2020-01-01",
            fallback_description="Fallback text",
            rating_distribution={"4.5": 3},
        )
        mock_books_client.get_book = mocker.AsyncMock(
            return_value=app.proto.books_pb2.BookDetailResponse(book=detail)
        )

        response = client.get("/api/v1/books/dune")

        data = response.json()["data"]
        assert data["avg_rating"] == 4.25
        assert data["fallback_description"] == "Fallback text"
        assert data["fallback_language"] is None
        assert data["first_sentence"] is None
        assert data["series"] is None
        assert data["series_position"] is None
        assert data["rating_distribution"] == {"4.5": 3}


class TestSearchMapping:
    def test_search_results_keep_int64_ids_as_numbers(
        self, client, mock_books_client, mocker
    ):
        mock_books_client.search_books_and_authors = mocker.AsyncMock(
            return_value=app.proto.books_pb2.SearchResponse(
                results=[
                    app.proto.books_pb2.SearchResult(
                        type="book",
                        id=2**40,
                        title="Dune",
                        slug="dune",
                        app_avg_rating=4.5,
                    )
                ],
                total_count=1,
            )
        )

        response = client.get("/api/v1/search?q=dune")

        result = response.json()["data"]["results"][0]
        assert result["id"] == 2**40
        assert result["app_avg_rating"] == 4.5
        assert result["work_id"] is None
        assert result["language"] is None
