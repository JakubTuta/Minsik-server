import app.services.author_store as authors
import app.workers.dump.phases.authors as authors_phase


def entry(ol_id: str, name: str = "John Smith") -> dict:
    return {"open_library_id": ol_id, "name": name, "base_slug": "john-smith"}


def test_the_first_holder_keeps_the_plain_slug() -> None:
    resolved = authors.assign_slugs([entry("OL1A")], {})

    assert resolved[0]["slug"] == "john-smith"


def test_a_namesake_gets_their_openlibrary_id_appended() -> None:
    resolved = authors.assign_slugs([entry("OL1A"), entry("OL2A")], {})

    assert [row["slug"] for row in resolved] == ["john-smith", "john-smith-ol2a"]


def test_the_holder_of_a_slug_keeps_it_on_a_later_run() -> None:
    resolved = authors.assign_slugs([entry("OL1A")], {"john-smith": "OL1A"})

    assert resolved[0]["slug"] == "john-smith"


def test_a_namesake_of_an_existing_author_is_not_merged_into_it() -> None:
    resolved = authors.assign_slugs([entry("OL2A")], {"john-smith": "OL1A"})

    assert resolved[0]["slug"] == "john-smith-ol2a"


def test_an_author_without_an_openlibrary_id_is_adopted_once() -> None:
    owners: dict = {"john-smith": None}
    resolved = authors.assign_slugs([entry("OL1A"), entry("OL2A")], owners)

    assert [row["slug"] for row in resolved] == ["john-smith", "john-smith-ol2a"]
    assert owners["john-smith"] == "OL1A"


def test_a_dump_author_without_a_name_or_id_is_skipped() -> None:
    assert authors_phase.parse_author({"key": "/authors/OL1A"}) is None
    assert authors_phase.parse_author({"name": "Anna", "bio": "x" * 5}) is None
