import app.services._language_boost as language_boost
import app.services.list_builder as list_builder


class TestPreferredEditionSql:
    def test_orders_reader_language_first_then_english(self):
        sql = language_boost.preferred_edition_sql()

        assert sql.index("pe.language = :language") < sql.index("pe.language = 'en'")

    def test_matches_on_work_not_language(self):
        sql = language_boost.preferred_edition_sql()

        assert "pe.work_id = b.work_id" in sql

    def test_extra_where_constrains_the_picker(self):
        # Without this, the picker can elect an edition the outer query then
        # rejects, dropping the whole work from the list.
        sql = language_boost.preferred_edition_sql(
            extra_where="pe.first_sentence IS NOT NULL"
        )

        assert "pe.first_sentence IS NOT NULL" in sql

    def test_cover_requirement_is_optional(self):
        assert "primary_cover_url" not in language_boost.preferred_edition_sql(
            require_cover=False
        )


class TestBookBaseWhere:
    def test_does_not_hard_filter_candidates_by_language(self):
        # Candidate selection must stay language-agnostic: filtering the pool
        # down to one language leaves readers of a thin catalog with a
        # near-empty list instead of the globally best works.
        assert "b.language = :language" not in list_builder._BOOK_BASE_WHERE

    def test_keeps_one_edition_per_work(self):
        assert "b.book_id = (" in list_builder._BOOK_BASE_WHERE
        assert "pe.work_id = b.work_id" in list_builder._BOOK_BASE_WHERE


class TestDedupeByWork:
    def test_prefers_the_reader_language_edition(self):
        items = [
            {"work_id": "W1", "language": "en", "score": 9, "readers": 100},
            {"work_id": "W1", "language": "pl", "score": 1, "readers": 100},
        ]

        result = language_boost.dedupe_by_work(items, "pl")

        assert len(result) == 1
        assert result[0]["language"] == "pl"

    def test_does_not_inflate_readers_across_editions(self):
        # Reader counts are pooled per work in SQL, so every edition already
        # carries the work total; summing them would multiply by edition count.
        items = [
            {"work_id": "W1", "language": "en", "score": 5, "readers": 100},
            {"work_id": "W1", "language": "de", "score": 4, "readers": 100},
        ]

        result = language_boost.dedupe_by_work(items, "pl")

        assert len(result) == 1
        assert result[0]["readers"] == 100

    def test_falls_back_to_most_read_edition_when_language_absent(self):
        items = [
            {"work_id": "W1", "language": "en", "score": 1, "readers": 500},
            {"work_id": "W1", "language": "de", "score": 9, "readers": 40},
        ]

        result = language_boost.dedupe_by_work(items, "pl")

        assert result[0]["language"] == "en"

    def test_keeps_distinct_works_apart(self):
        items = [
            {"work_id": "W1", "language": "en", "score": 1, "readers": 10},
            {"work_id": "W2", "language": "en", "score": 2, "readers": 20},
        ]

        assert len(language_boost.dedupe_by_work(items, "en")) == 2
