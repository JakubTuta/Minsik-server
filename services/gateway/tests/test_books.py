import app.grpc_clients
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


def make_book_summary(mocker, book_id=1, first_sentence=""):
    book = mocker.MagicMock()
    book.book_id = book_id
    book.work_id = f"OL{book_id}W"
    book.language = "en"
    book.title = f"Book {book_id}"
    book.slug = f"book-{book_id}"
    book.description = ""
    book.original_publication_year = 1949
    book.primary_cover_url = "https://example.com/cover.jpg"
    book.authors = []
    book.rating_count = 10
    book.avg_rating = "4.50"
    book.ol_rating_count = 5
    book.ol_avg_rating = "4.00"
    book.ol_want_to_read_count = 1
    book.ol_currently_reading_count = 1
    book.ol_already_read_count = 1
    book.app_want_to_read_count = 1
    book.app_reading_count = 1
    book.app_read_count = 1
    book.series_position = ""
    book.rarity = "rare"
    book.first_sentence = first_sentence
    return book


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
            make_book_summary(mocker, 1),
            make_book_summary(mocker, 2, first_sentence="It was a bright cold day."),
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
        books_response.books = [make_book_summary(mocker, 1)]
        mock_books_client.get_author_books = mocker.AsyncMock(
            return_value=books_response
        )

        response = client.get("/api/v1/authors/george-orwell/quote")

        assert response.status_code == 200
        assert response.json()["data"] is None
