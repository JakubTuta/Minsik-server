import app.workers.dump.parsers as parsers
import app.workers.dump.phases.editions as editions_phase
import app.workers.dump.phases.merge as merge
import pytest

ENGLISH = "A young wizard discovers that he is the hero of a prophecy and must travel across the land."
POLISH = "Młody czarodziej odkrywa, że jest bohaterem przepowiedni i musi wyruszyć w podróż przez krainę."
GERMAN = "Ein junger Zauberer entdeckt, dass er der Held einer Prophezeiung ist und durch das Land reisen muss."


def work(**overrides) -> dict:
    base = {
        "work_ol_id": "OL1W",
        "title": "Earthsea",
        "title_language": None,
        "description": ENGLISH,
        "description_language": "en",
        "first_sentence": None,
        "first_publish_year": 1968,
        "cover_url": "https://covers/1.jpg",
    }
    return {**base, **overrides}


def edition(**payload) -> dict:
    base = {
        "title": None, "description": None, "first_sentence": None, "isbns": [], "number_of_pages": None,
        "publisher": None, "physical_format": None, "external_ids": {"work_ol_id": "OL1W"},
        "open_library_id": None, "google_books_id": None, "cover_url": None, "series": None,
    }
    return {**base, **payload}


def existing(book_id: int, language: str, **overrides) -> dict:
    base = {
        "book_id": book_id, "language": language, "slug": "earthsea", "title": "Earthsea", "description": None,
        "first_sentence": None, "edition_source": "legacy", "manually_edited_fields": [],
        "original_publication_year": 1968, "primary_cover_url": None, "isbn": [], "publisher": None,
        "number_of_pages": None, "external_ids": {"work_ol_id": "OL1W"}, "open_library_id": "OL1W",
        "google_books_id": None,
    }
    return {**base, **overrides}


def by_language(plans: list[merge.RowPlan]) -> dict[str, merge.RowPlan]:
    return {plan.language: plan for plan in plans}


def test_each_language_row_gets_only_its_own_text() -> None:
    plans = by_language(merge.plan_work(
        work(),
        {"pl": edition(title="Ziemiomorze", description=POLISH), "de": edition(title="Erdsee")},
        {},
    ))

    assert set(plans) == {"en", "pl", "de"}
    assert (plans["en"].title, plans["en"].description) == ("Earthsea", ENGLISH)
    assert (plans["pl"].title, plans["pl"].description) == ("Ziemiomorze", POLISH)
    assert plans["de"].title == "Erdsee"
    assert plans["de"].description is None


def test_work_text_does_not_leak_into_a_translation() -> None:
    plans = by_language(merge.plan_work(work(), {"pl": edition()}, {}))

    assert plans["pl"].description is None
    assert plans["en"].description == ENGLISH


def test_existing_rows_keep_their_book_id() -> None:
    plans = by_language(merge.plan_work(
        work(), {"pl": edition(title="Ziemiomorze")},
        {"en": existing(10, "en"), "pl": existing(11, "pl", slug="earthsea")},
    ))

    assert plans["en"].book_id == 10
    assert plans["pl"].book_id == 11


def test_a_copied_original_title_gives_way_to_the_editions_own() -> None:
    plans = by_language(merge.plan_work(
        work(), {"pl": edition(title="Ziemiomorze")}, {"pl": existing(11, "pl", title="Earthsea")},
    ))
    assert plans["pl"].title == "Ziemiomorze"


def test_a_real_existing_translation_title_is_not_replaced() -> None:
    plans = by_language(merge.plan_work(
        work(), {"pl": edition(title="Czarnoksiężnik z Archipelagu")},
        {"pl": existing(11, "pl", title="Ziemiomorze", slug="ziemiomorze")},
    ))
    assert plans["pl"].title == "Ziemiomorze"


def test_wrong_language_text_already_on_a_row_is_replaced_not_kept() -> None:
    plans = by_language(merge.plan_work(
        work(), {"pl": edition(description=POLISH)}, {"pl": existing(11, "pl", description=ENGLISH)},
    ))
    assert plans["pl"].description == POLISH


def test_wrong_language_text_without_a_replacement_is_cleared() -> None:
    plans = by_language(merge.plan_work(work(), {"pl": edition()}, {"pl": existing(11, "pl", description=ENGLISH)}))
    assert plans["pl"].description is None


def test_text_in_the_rows_own_language_is_kept_over_new_text() -> None:
    plans = by_language(merge.plan_work(
        work(), {"pl": edition(description=POLISH)}, {"pl": existing(11, "pl", description="Mój opis, że jest w moim języku i nie do zmiany.")},
    ))
    assert plans["pl"].description.startswith("Mój opis")


def test_manually_edited_fields_are_never_touched() -> None:
    plans = by_language(merge.plan_work(
        work(), {},
        {"en": existing(10, "en", title="Admin title", description="Admin text", manually_edited_fields=["title", "description"])},
    ))
    assert plans["en"].title == "Admin title"
    assert plans["en"].description == "Admin text"


def test_a_manual_row_stays_manual() -> None:
    plans = by_language(merge.plan_work(work(), {}, {"en": existing(10, "en", edition_source="manual")}))
    assert plans["en"].edition_source == "manual"


def test_language_neutral_edition_fills_facts_but_no_text() -> None:
    plans = by_language(merge.plan_work(
        work(), {"": edition(title="Ignored", description="Ignored", isbns=["9780000000001"], number_of_pages=300, publisher="Penguin")}, {},
    ))

    assert set(plans) == {"en"}
    assert plans["en"].isbn == ["9780000000001"]
    assert (plans["en"].number_of_pages, plans["en"].publisher) == (300, "Penguin")
    assert plans["en"].description == ENGLISH


def test_a_placeholder_english_row_of_a_polish_work_is_relabelled_in_place() -> None:
    polish_work = work(title="Pan Tadeusz", description=POLISH, description_language="pl")
    plans = merge.plan_work(polish_work, {}, {"en": existing(10, "en", title="Pan Tadeusz", slug="pan-tadeusz")})

    assert [plan.language for plan in plans] == ["pl"]
    assert plans[0].book_id == 10
    assert plans[0].previous_language == "en"
    assert plans[0].slug is None


def test_an_english_row_backed_by_an_english_edition_is_not_relabelled() -> None:
    polish_work = work(description=POLISH, description_language="pl")
    plans = by_language(merge.plan_work(polish_work, {"en": edition(title="Earthsea")}, {"en": existing(10, "en")}))

    assert set(plans) == {"en", "pl"}
    assert plans["en"].book_id == 10
    assert plans["pl"].book_id is None


def test_a_manually_edited_row_is_not_relabelled() -> None:
    polish_work = work(description=POLISH, description_language="pl")
    plans = by_language(merge.plan_work(
        polish_work, {}, {"en": existing(10, "en", manually_edited_fields=["language"])}
    ))
    assert set(plans) == {"pl"}
    assert plans["pl"].book_id is None


def test_new_rows_get_distinct_slugs_per_language() -> None:
    first, second = merge.plan_work(work(), {}, {}), merge.plan_work(work(work_ol_id="OL2W"), {}, {})
    taken: set[tuple[str, str]] = set()
    merge.assign_slugs(first, taken)
    merge.assign_slugs(second, taken)

    assert first[0].slug == "earthsea"
    assert second[0].slug == "earthsea-ol2w"


def test_an_existing_slug_is_kept_while_the_title_is_unchanged() -> None:
    plans = merge.plan_work(work(), {}, {"en": existing(10, "en", slug="earthsea")})
    merge.assign_slugs(plans, {("en", "earthsea")})

    assert plans[0].slug == "earthsea"


def test_a_slug_that_followed_a_replaced_title_is_regenerated() -> None:
    plans = merge.plan_work(
        work(), {"pl": edition(title="Ziemiomorze")}, {"pl": existing(11, "pl", title="Earthsea", slug="earthsea")},
    )
    pl = by_language(plans)["pl"]
    merge.assign_slugs([pl], {("pl", "earthsea")})

    assert pl.slug == "ziemiomorze"
    assert pl.previous_slug == "earthsea"


def test_a_custom_slug_survives_a_title_change() -> None:
    plans = merge.plan_work(
        work(), {"pl": edition(title="Ziemiomorze")}, {"pl": existing(11, "pl", title="Earthsea", slug="my-custom-slug")},
    )
    pl = by_language(plans)["pl"]
    merge.assign_slugs([pl], {("pl", "my-custom-slug")})

    assert pl.slug == "my-custom-slug"


def edition_data(**overrides) -> dict:
    base = {
        "key": "/books/OL9M", "works": [{"key": "/works/OL1W"}], "title": "Ziemiomorze",
        "languages": [{"key": "/languages/pol"}], "description": POLISH, "isbn_13": ["9780306406157"],
        "number_of_pages": 320, "publishers": ["Zysk"], "covers": [12],
    }
    return {**base, **overrides}


def known_filter() -> bytearray:
    flags = bytearray(parsers._KNOWN_WORKS_MAX_ID // 8 + 1)
    flags[1 // 8] |= 1 << (1 % 8)
    return flags


def test_a_tagged_edition_stages_under_its_language() -> None:
    candidate = editions_phase.parse_edition(edition_data(), known_filter())

    assert candidate["language"] == "pl"
    assert candidate["payload"]["title"] == "Ziemiomorze"
    assert candidate["payload"]["description"] == POLISH


def test_a_description_in_another_language_is_dropped_from_a_tagged_edition() -> None:
    candidate = editions_phase.parse_edition(edition_data(description=ENGLISH), known_filter())

    assert candidate["language"] == "pl"
    assert candidate["payload"]["description"] is None
    assert candidate["payload"]["number_of_pages"] == 320


def test_an_untagged_edition_is_not_assumed_to_be_english() -> None:
    candidate = editions_phase.parse_edition(edition_data(languages=[], title="Dune", description=None), known_filter())

    assert candidate["language"] == editions_phase.UNKNOWN_LANGUAGE
    assert candidate["payload"]["title"] is None
    assert candidate["payload"]["isbns"] == ["9780306406157"]


def test_an_untagged_edition_with_recognisable_text_is_placed_by_its_text() -> None:
    candidate = editions_phase.parse_edition(edition_data(languages=[], description=GERMAN, title="Erdsee"), known_filter())

    assert candidate["language"] == "de"
    assert candidate["payload"]["description"] == GERMAN


def test_an_edition_of_an_unknown_work_is_skipped() -> None:
    assert editions_phase.parse_edition(edition_data(works=[{"key": "/works/OL999W"}]), known_filter()) is None


@pytest.mark.parametrize("works", [[], None, "OL1W"])
def test_an_edition_without_a_usable_work_reference_is_skipped(works) -> None:
    assert editions_phase.parse_edition(edition_data(works=works), known_filter()) is None


def test_a_row_the_import_has_no_data_for_loses_text_in_the_wrong_language() -> None:
    rows = {
        "it": existing(20, "it", description=ENGLISH),
        "pt": existing(21, "pt", description="Texto sem sentido sem palavras comuns"),
        "ru": existing(22, "ru", description=ENGLISH, manually_edited_fields=["description"]),
        "pl": existing(23, "pl", description=ENGLISH),
    }

    stale = merge.stale_text_book_ids(rows, planned_languages={"pl"})

    assert stale["description"] == [20]


def test_a_relabelled_row_is_not_treated_as_stale() -> None:
    polish_work = work(description=POLISH, description_language="pl")
    rows = merge._relabel_placeholder(polish_work, {}, {"en": existing(10, "en", description=POLISH)})

    assert merge.stale_text_book_ids(rows, planned_languages={"pl"}) == {"description": [], "first_sentence": []}
