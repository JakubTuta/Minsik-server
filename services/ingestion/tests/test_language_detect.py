import app.workers.dump.language_detect as language_detect
import pytest

SAMPLES = [
    ("en", "A young wizard discovers that he is the hero of a prophecy and must travel across the land."),
    ("pl", "Młody czarodziej odkrywa, że jest bohaterem przepowiedni i musi wyruszyć w podróż przez krainę."),
    ("de", "Ein junger Zauberer entdeckt, dass er der Held einer Prophezeiung ist und durch das Land reisen muss."),
    ("es", "Un joven mago descubre que es el héroe de una profecía y debe viajar por la tierra."),
    ("fr", "Un jeune sorcier découvre qu'il est le héros d'une prophétie et doit voyager à travers le pays."),
    ("it", "Un giovane mago scopre che è l'eroe di una profezia e deve viaggiare per la terra."),
    ("pt", "Um jovem mago descobre que ele é o herói de uma profecia e não pode ficar em casa."),
    ("nl", "Een jonge tovenaar ontdekt dat hij de held is van een profetie en door het land moet reizen."),
    ("sv", "En ung trollkarl upptäcker att han är hjälten i en profetia och måste resa genom landet."),
    ("cs", "Mladý čaroděj zjistí, že je hrdinou proroctví a musí cestovat po celé zemi."),
    ("ru", "Молодой волшебник узнаёт, что он герой пророчества и должен отправиться в путешествие по земле."),
    ("uk", "Молодий чарівник дізнається, що він герой пророцтва і мусить вирушити в подорож країною, де є ґрунт."),
    ("ja", "若い魔法使いは自分が予言の英雄であることを知り、旅に出なければならない。"),
    ("zh", "年轻的巫师发现自己是预言中的英雄，必须穿越大地旅行。"),
    ("ko", "젊은 마법사는 자신이 예언의 영웅이라는 것을 알게 되고 여행을 떠나야 한다."),
    ("el", "Ένας νεαρός μάγος ανακαλύπτει ότι είναι ο ήρωας μιας προφητείας."),
]


@pytest.mark.parametrize(("language", "text"), SAMPLES)
def test_recognises_a_sentence_of_each_language(language: str, text: str) -> None:
    assert language_detect.detect(text) == language


def test_short_titles_are_not_guessed() -> None:
    assert language_detect.detect("Pan Tadeusz") is None
    assert language_detect.detect("Dune") is None
    assert language_detect.detect("") is None
    assert language_detect.detect(None) is None


def test_a_title_made_of_function_words_is_still_recognised() -> None:
    assert language_detect.detect("The Lord of the Rings") == "en"
    assert language_detect.detect("Der Herr der Ringe") == "de"


def test_an_ambiguous_mix_is_unclear_rather_than_wrong() -> None:
    assert language_detect.detect("la de el") is None


def test_numbers_and_punctuation_alone_say_nothing() -> None:
    assert language_detect.detect("1984 - 2024 !!! ???") is None


def test_fits_language_rejects_only_recognisable_foreign_text() -> None:
    english = SAMPLES[0][1]
    assert language_detect.fits_language(english, "en")
    assert not language_detect.fits_language(english, "pl")
    assert language_detect.fits_language("Pan Tadeusz", "pl")
    assert language_detect.fits_language("Pan Tadeusz", "en")
    assert language_detect.fits_language(None, "de")
