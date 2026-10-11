import app.workers.wikipedia as wikipedia
import pytest


@pytest.mark.parametrize(
    ("page", "expected", "matches"),
    [
        ("The Hobbit", "The Hobbit", True),
        ("The Hobbit (novel)", "Hobbit", True),
        ("Hobbit, czyli tam i z powrotem", "Hobbit", False),
        ("The Hobbit: An Unexpected Journey", "The Hobbit", False),
        ("Pan Tadeusz", "pan tadeusz", True),
        ("Wiedźmin", "Wiedzmin", True),
        ("Dune (1984 film)", "Dune", False),
        ("Dune (novel)", "Dune", True),
        ("Gra o tron (gra komputerowa)", "Gra o tron", False),
        ("Dune Messiah", "Dune", False),
        ("", "Dune", False),
    ],
)
def test_a_page_is_accepted_only_when_its_title_is_the_entitys(page: str, expected: str, matches: bool) -> None:
    assert wikipedia.title_matches(page, expected) is matches


def test_an_extract_must_name_the_books_author() -> None:
    extract = "The Hobbit is a children's fantasy novel by English author J. R. R. Tolkien."

    assert wikipedia.mentions_author(extract, "J. R. R. Tolkien")
    assert not wikipedia.mentions_author(extract, "Terry Pratchett")


def test_without_an_author_there_is_nothing_to_check() -> None:
    assert wikipedia.mentions_author("Anything at all.", None)


def test_an_author_name_too_short_to_identify_anyone_is_not_trusted() -> None:
    assert not wikipedia.mentions_author("Li wrote this.", "A Li")
