import datetime
import typing

import pytest
from app.workers.dump_importer import (
    _OL_LANG_TO_ISO,
    _extract_cover_url,
    _extract_description,
    _extract_ol_lang,
    _extract_remote_ids,
    _extract_text_value,
    _is_wikidata_qid,
    _parse_free_date,
    _parse_series_string,
    _score_edition,
)


class TestExtractTextValue:
    def test_string_value(self):
        assert _extract_text_value("hello") == "hello"

    def test_dict_value(self):
        assert (
            _extract_text_value({"type": "/type/text", "value": "some text"})
            == "some text"
        )

    def test_none(self):
        assert _extract_text_value(None) is None

    def test_int(self):
        assert _extract_text_value(42) is None

    def test_dict_missing_value(self):
        assert _extract_text_value({"type": "/type/text"}) is None


class TestExtractDescription:
    def test_string_description(self):
        result = _extract_description("A great book about coding")
        assert result is not None
        assert "great book" in result

    def test_dict_description(self):
        result = _extract_description(
            {"type": "/type/text", "value": "Detailed plot summary"}
        )
        assert result is not None
        assert "plot summary" in result

    def test_none_description(self):
        assert _extract_description(None) is None


class TestExtractCoverUrl:
    def test_valid_cover(self):
        url = _extract_cover_url([12345])
        assert url == "https://covers.openlibrary.org/b/id/12345-L.jpg"

    def test_skips_negative(self):
        url = _extract_cover_url([-1, 12345])
        assert url == "https://covers.openlibrary.org/b/id/12345-L.jpg"

    def test_empty_list(self):
        assert _extract_cover_url([]) is None

    def test_none(self):
        assert _extract_cover_url(None) is None

    def test_all_invalid(self):
        assert _extract_cover_url([-1, -2, 0]) is None


class TestParseFreeDate:
    def test_full_date(self):
        result = _parse_free_date("1984-07-01")
        assert result is not None
        assert result.year == 1984

    def test_year_only(self):
        result = _parse_free_date("1984")
        assert result is not None
        assert result.year == 1984

    def test_none(self):
        assert _parse_free_date(None) is None

    def test_empty_string(self):
        assert _parse_free_date("") is None

    def test_garbage(self):
        assert _parse_free_date("not a date") is None


class TestExtractRemoteIds:
    def test_valid_remote_ids(self):
        author = {
            "remote_ids": {
                "wikidata": "Q123",
                "viaf": "456",
                "isni": "789",
            }
        }
        result = _extract_remote_ids(author)
        assert result == {"wikidata": "Q123", "viaf": "456", "isni": "789"}

    def test_empty_remote_ids(self):
        assert _extract_remote_ids({"remote_ids": {}}) == {}

    def test_missing_remote_ids(self):
        assert _extract_remote_ids({}) == {}

    def test_filters_empty_values(self):
        author = {"remote_ids": {"wikidata": "Q123", "empty": ""}}
        result = _extract_remote_ids(author)
        assert result == {"wikidata": "Q123"}

    def test_filters_non_string_values(self):
        author = {"remote_ids": {"wikidata": "Q123", "bad": 42}}
        result = _extract_remote_ids(author)
        assert result == {"wikidata": "Q123"}


class TestExtractOlLang:
    def test_dict_english(self):
        assert _extract_ol_lang({"key": "/languages/eng"}) == "en"

    def test_dict_french(self):
        assert _extract_ol_lang({"key": "/languages/fre"}) == "fr"

    def test_dict_german(self):
        assert _extract_ol_lang({"key": "/languages/ger"}) == "de"

    def test_string_format(self):
        assert _extract_ol_lang("/languages/spa") == "es"

    def test_unknown_language(self):
        assert _extract_ol_lang({"key": "/languages/zzz"}) is None

    def test_none(self):
        assert _extract_ol_lang(None) is None

    def test_coverage_of_common_languages(self):
        common = ["eng", "fre", "ger", "spa", "ita", "por", "rus", "jpn", "chi", "kor"]
        for code in common:
            result = _extract_ol_lang({"key": f"/languages/{code}"})
            assert result is not None, f"Missing mapping for {code}"


class TestParseSeriesString:
    def test_series_with_number(self):
        result = _parse_series_string(["Harry Potter #3"])
        assert result is not None
        assert result["name"] == "Harry Potter"
        assert result["position"] == 3.0

    def test_series_with_decimal(self):
        result = _parse_series_string(["Discworld #2.5"])
        assert result is not None
        assert result["name"] == "Discworld"
        assert result["position"] == 2.5

    def test_series_without_number(self):
        result = _parse_series_string(["Lord of the Rings"])
        assert result is not None
        assert result["name"] == "Lord of the Rings"
        assert result["position"] is None

    def test_none_input(self):
        assert _parse_series_string(None) is None

    def test_empty_list(self):
        assert _parse_series_string([]) is None

    def test_comma_separator(self):
        result = _parse_series_string(["Foundation, 1"])
        assert result is not None
        assert result["name"] == "Foundation"
        assert result["position"] == 1.0


class TestScoreEdition:
    def test_empty_edition(self):
        assert _score_edition({}) == 0

    def test_full_edition(self):
        edition = {
            "isbn_13": ["9780441569595"],
            "number_of_pages": 271,
            "publishers": ["Ace Books"],
            "covers": [12345],
            "description": "A cyberpunk novel",
            "physical_format": "Hardcover",
        }
        assert _score_edition(edition) == 6

    def test_partial_edition(self):
        edition = {
            "isbn_10": ["0441569595"],
            "publishers": ["Ace Books"],
        }
        assert _score_edition(edition) == 2

    def test_invalid_page_count(self):
        edition = {
            "number_of_pages": -1,
        }
        assert _score_edition(edition) == 0

    def test_zero_page_count(self):
        edition = {
            "number_of_pages": 0,
        }
        assert _score_edition(edition) == 0


class TestIsWikidataQid:
    def test_valid_qid(self):
        assert _is_wikidata_qid("Q42") is True

    def test_large_qid(self):
        assert _is_wikidata_qid("Q188987") is True

    def test_label_not_qid(self):
        assert _is_wikidata_qid("United States") is False

    def test_empty_string(self):
        assert _is_wikidata_qid("") is False

    def test_q_only(self):
        assert _is_wikidata_qid("Q") is False

    def test_property_id(self):
        assert _is_wikidata_qid("P27") is False


class TestLanguageMapping:
    def test_all_values_are_two_letter_codes(self):
        for marc_code, iso_code in _OL_LANG_TO_ISO.items():
            assert (
                len(iso_code) == 2
            ), f"ISO code for {marc_code} is not 2 chars: {iso_code}"

    def test_no_duplicate_marc_codes(self):
        assert len(_OL_LANG_TO_ISO) == len(set(_OL_LANG_TO_ISO.keys()))

    def test_common_languages_mapped(self):
        assert _OL_LANG_TO_ISO["eng"] == "en"
        assert _OL_LANG_TO_ISO["fre"] == "fr"
        assert _OL_LANG_TO_ISO["ger"] == "de"
        assert _OL_LANG_TO_ISO["spa"] == "es"
        assert _OL_LANG_TO_ISO["jpn"] == "ja"
        assert _OL_LANG_TO_ISO["chi"] == "zh"
        assert _OL_LANG_TO_ISO["rus"] == "ru"
        assert _OL_LANG_TO_ISO["ara"] == "ar"
        assert _OL_LANG_TO_ISO["kor"] == "ko"
        assert _OL_LANG_TO_ISO["pol"] == "pl"
