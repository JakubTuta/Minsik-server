from unittest.mock import AsyncMock, patch

import app.services.search_service as search_service
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_cache():
    with patch("app.cache.get_cached", return_value=None), patch(
        "app.cache.set_cached", return_value=None
    ):
        yield


def _book(id_, score, work_id=None):
    return {
        "type": "book",
        "id": id_,
        "title": f"Book {id_}",
        "slug": f"book-{id_}",
        "work_id": work_id or f"work-{id_}",
        "cover_url": "",
        "authors": [],
        "relevance_score": score,
        "author_slugs": [],
        "series_slug": "",
        "app_avg_rating": None,
        "app_rating_count": 0,
        "ol_avg_rating": None,
        "ol_rating_count": 0,
        "readers": 0,
        "book_count": 0,
        "language": "en",
    }


def _author(id_, score):
    return {
        "type": "author",
        "id": id_,
        "title": f"Author {id_}",
        "slug": f"author-{id_}",
        "work_id": "",
        "cover_url": "",
        "authors": [],
        "relevance_score": score,
        "author_slugs": [],
        "series_slug": "",
        "app_avg_rating": None,
        "app_rating_count": 0,
        "ol_avg_rating": None,
        "ol_rating_count": 0,
        "readers": 0,
        "book_count": 0,
        "language": "",
    }


def _kind_filter(query_body):
    return query_body["bool"]["filter"][0]["term"]["kind"]


class TestSearchBooksAndAuthors:
    @pytest.mark.asyncio
    async def test_search_all_types_runs_one_unfiltered_query(self, mock_session, mock_cache):
        with patch(
            "app.services.search_service._run_search", new=AsyncMock(return_value=([], 0))
        ) as mock_run:
            results, total = await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="all"
            )

        assert results == []
        assert total == 0
        query_body = mock_run.call_args.args[0]
        assert "filter" not in query_body["bool"]

    @pytest.mark.asyncio
    async def test_type_filter_maps_to_a_kind_filter(self, mock_session, mock_cache):
        with patch(
            "app.services.search_service._run_search", new=AsyncMock(return_value=([], 0))
        ) as mock_run:
            await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="authors"
            )

        query_body = mock_run.call_args.args[0]
        assert _kind_filter(query_body) == "author"

    @pytest.mark.asyncio
    async def test_search_books_only(self, mock_session, mock_cache):
        mock_books = [_book(1, 0.9)]

        with patch(
            "app.services.search_service._run_search",
            new=AsyncMock(return_value=(mock_books, 1)),
        ):
            results, total = await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="books"
            )

        assert len(results) == 1
        assert results[0]["type"] == "book"
        assert total == 1

    @pytest.mark.asyncio
    async def test_pagination_is_passed_straight_to_elasticsearch(self, mock_session, mock_cache):
        with patch(
            "app.services.search_service._run_search", new=AsyncMock(return_value=([], 0))
        ) as mock_run:
            await search_service.search_books_and_authors(
                mock_session, query="test", limit=5, offset=15, type_filter="books"
            )

        _query_body, _rescore, from_, size, _min_score, _language = mock_run.call_args.args
        assert from_ == 15
        assert size == 5

    @pytest.mark.asyncio
    async def test_zero_hits_falls_back_to_a_fuzzy_pass(self, mock_session, mock_cache):
        fuzzy_books = [_book(1, 0.4)]
        run_search = AsyncMock(side_effect=[([], 0), (fuzzy_books, 1)])

        with patch("app.services.search_service._run_search", new=run_search):
            results, total = await search_service.search_books_and_authors(
                mock_session, query="hobbti", limit=10, offset=0, type_filter="books"
            )

        assert run_search.call_count == 2
        assert total == 1
        assert results == fuzzy_books
        # The strict pass floors on min_score; the fuzzy retry drops the floor
        # entirely, since a fuzzy match already starts weaker than an exact one.
        fuzzy_min_score = run_search.call_args_list[1].args[4]
        assert fuzzy_min_score == 0.0

    @pytest.mark.asyncio
    async def test_nonzero_hits_never_trigger_the_fuzzy_fallback(self, mock_session, mock_cache):
        run_search = AsyncMock(return_value=([_book(1, 0.9)], 1))

        with patch("app.services.search_service._run_search", new=run_search):
            await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="books"
            )

        assert run_search.call_count == 1


class TestEditionSelection:
    EDITIONS = [
        {"book_id": 1, "language": "en", "slug": "the-witcher", "ratings": 40},
        {"book_id": 2, "language": "pl", "slug": "wiedzmin", "ratings": 10},
        {"book_id": 3, "language": "de", "slug": "der-hexer", "ratings": 90},
    ]

    def test_readers_language_wins(self):
        assert search_service.select_edition(self.EDITIONS, "pl")["book_id"] == 2

    def test_english_is_the_first_fallback(self):
        assert search_service.select_edition(self.EDITIONS, "fr")["book_id"] == 1

    def test_most_rated_edition_when_neither_exists(self):
        editions = [e for e in self.EDITIONS if e["language"] != "en"]

        assert search_service.select_edition(editions, "fr")["book_id"] == 3


class TestQueryShape:
    def test_dis_max_wraps_every_text_tier(self):
        profile = search_service._search_profile()
        query = search_service._build_query("hobbit", profile, kind=None)

        dis_max = query["bool"]["must"][0]["dis_max"]
        assert dis_max["tie_breaker"] == 0.1
        # exact + prefix + phrase(base) + recall, at minimum.
        assert len(dis_max["queries"]) >= 4

    def test_kind_filter_present_only_when_a_type_is_requested(self):
        profile = search_service._search_profile()

        assert "filter" not in search_service._build_query("hobbit", profile, kind=None)["bool"]
        assert search_service._build_query("hobbit", profile, kind="book")["bool"]["filter"] == [
            {"term": {"kind": "book"}}
        ]

    def test_suggest_profile_omits_the_loose_recall_tier(self):
        search_query = search_service._build_query("hobbit", search_service._search_profile(), kind=None)
        suggest_query = search_service._build_query("hobbit", search_service._suggest_profile(), kind=None)

        search_clause_count = len(search_query["bool"]["must"][0]["dis_max"]["queries"])
        suggest_clause_count = len(suggest_query["bool"]["must"][0]["dis_max"]["queries"])

        assert suggest_clause_count == search_clause_count - 1

    def test_fuzzy_pass_adds_exactly_one_extra_clause(self):
        profile = search_service._search_profile()
        strict = search_service._build_query("hobbit", profile, kind=None, fuzzy=False)
        fuzzy = search_service._build_query("hobbit", profile, kind=None, fuzzy=True)

        strict_count = len(strict["bool"]["must"][0]["dis_max"]["queries"])
        fuzzy_count = len(fuzzy["bool"]["must"][0]["dis_max"]["queries"])

        assert fuzzy_count == strict_count + 1

    def test_language_is_a_tie_break_not_a_filter(self):
        clauses = search_service._signal_clauses("pl")
        language_clauses = [clause for clause in clauses if "terms" in clause]

        assert language_clauses[0]["terms"]["languages"] == ["pl"]
        assert language_clauses[0]["terms"]["boost"] < 1.0

    def test_suggest_weighs_popularity_harder_than_search(self):
        search_rescore = search_service._build_rescore("en", search_service._search_profile())
        suggest_rescore = search_service._build_rescore("en", search_service._suggest_profile())

        assert (
            suggest_rescore["query"]["rescore_query_weight"]
            > search_rescore["query"]["rescore_query_weight"]
        )


class TestSuggestBuckets:
    @pytest.mark.asyncio
    async def test_every_kind_is_queried_independently(self, mock_cache):
        run_search = AsyncMock(return_value=([], 0))

        with patch("app.services.search_service._run_search", new=run_search):
            await search_service.suggest("hobbit", limit=20, language="en")

        # Strict pass queries all three kinds; all buckets come back empty,
        # so a fuzzy retry queries all three again.
        assert run_search.call_count == 6
        queried_kinds = [_kind_filter(call.args[0]) for call in run_search.call_args_list[:3]]
        assert sorted(queried_kinds) == ["author", "book", "series"]

    @pytest.mark.asyncio
    async def test_a_landslide_of_one_kind_cannot_crowd_out_another(self, mock_cache):
        books = [_book(i, 1.0 - i / 100) for i in range(10)]

        async def fake_run_search(query_body, _rescore, _from, _size, _min_score, _language):
            if _kind_filter(query_body) == "book":
                return books, len(books)
            return [], 0

        with patch(
            "app.services.search_service._run_search",
            new=AsyncMock(side_effect=fake_run_search),
        ):
            results = await search_service.suggest("hobbit", limit=20, language="en")

        # 10 books matched but the book bucket caps at 5 regardless.
        assert len(results) == 5
        assert all(r["type"] == "book" for r in results)

    @pytest.mark.asyncio
    async def test_no_fuzzy_retry_when_any_bucket_has_results(self, mock_cache):
        async def fake_run_search(query_body, _rescore, _from, _size, _min_score, _language):
            if _kind_filter(query_body) == "author":
                return [_author(1, 0.9)], 1
            return [], 0

        run_search = AsyncMock(side_effect=fake_run_search)
        with patch("app.services.search_service._run_search", new=run_search):
            results = await search_service.suggest("test", limit=20, language="en")

        assert run_search.call_count == 3
        assert any(r["type"] == "author" for r in results)
