"""Language detection for catalogue text. No model files, no dependencies.

The importer needs one decision: is this description or title written in the
language of the row it is about to fill? A wrong "yes" is how an English blurb
ended up on every Polish page, so the detector answers `None` ("cannot tell")
rather than guess, and callers treat `None` as no evidence either way.

Non-Latin scripts are told apart by their alphabet. Latin-script languages are
scored by how many of their most frequent function words the text contains; that
is very reliable from about a sentence on and useless for a one-word title, which
is why short text comes back as `None`.
"""

import collections
import re
import unicodedata

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

MIN_TOKENS = 3
MIN_HITS = 2

_STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        "the of and to in is was with for his her that he she it as by on at from who their they "
        "which are this be an has had not but one about after into when its were been have".split()
    ),
    "pl": frozenset(
        "i w na z się nie to że do jest jak ale po co który która które dla przez od są jego jej "
        "tym oraz także tylko czy już gdy przed pod ich być był była było jako lub tego".split()
    ),
    "de": frozenset(
        "der die das und ist nicht ein eine mit von zu den dem des auf für sich im als auch er sie "
        "es wird werden nach bei aus dass wie über oder zum zur einem einer einen sind war".split()
    ),
    "es": frozenset(
        "el la los las de que y en un una es por con para su se del al más como pero sus le ya o "
        "este porque esta entre cuando muy sin sobre también fue son".split()
    ),
    "fr": frozenset(
        "le la les de des du un une et est en que qui dans pour pas sur au aux ce il elle ne se "
        "son sa ses par avec plus mais ou où comme cette sont été qu".split()
    ),
    "it": frozenset(
        "il lo la i gli le di che e è un una in per con non su come ma anche del della dei delle "
        "nel nella sono più suo sua alla dal degli".split()
    ),
    "pt": frozenset(
        "o a os as de do da dos das que e é um uma em para com não por mais como mas foi ao ele "
        "ela seu sua também são nos pelo pela".split()
    ),
    "nl": frozenset(
        "de het een en van in is dat op te voor met zijn niet aan er ook als maar om bij naar over "
        "uit deze wordt werd door hij zij".split()
    ),
    "sv": frozenset(
        "och att det som en ett är på av för med den till inte har de om men var sig från han hon "
        "ska också".split()
    ),
    "cs": frozenset(
        "a v se na je že s z do to jako ale pro po který která které byl byla jsou jeho její nebo "
        "při tak však".split()
    ),
    "tr": frozenset("ve bir bu için ile de da çok ama olarak gibi daha kadar ne değil sonra her".split()),
    "ru": frozenset(
        "и в не на что он с как это по но из его она они был для от все так же или при".split()
    ),
    "uk": frozenset(
        "і в не на що він з як це по але із його вона вони був для від та й також або при".split()
    ),
}

_UKRAINIAN_ONLY = frozenset("ґєії")

# (first, last) code points of the blocks that identify a script.
_SCRIPT_BLOCKS: dict[str, tuple[tuple[int, int], ...]] = {
    "hiragana_katakana": ((0x3040, 0x30FF),),
    "han": ((0x4E00, 0x9FFF), (0x3400, 0x4DBF)),
    "hangul": ((0xAC00, 0xD7AF), (0x1100, 0x11FF)),
    "greek": ((0x0370, 0x03FF),),
    "hebrew": ((0x0590, 0x05FF),),
    "arabic": ((0x0600, 0x06FF),),
    "thai": ((0x0E00, 0x0E7F),),
    "devanagari": ((0x0900, 0x097F),),
    "cyrillic": ((0x0400, 0x04FF),),
}

_LANGUAGE_BY_SCRIPT = {
    "hiragana_katakana": "ja",
    "han": "zh",
    "hangul": "ko",
    "greek": "el",
    "hebrew": "he",
    "arabic": "ar",
    "thai": "th",
    "devanagari": "hi",
}

_NON_LATIN_SHARE = 0.5


def _script_of(char: str) -> str | None:
    code = ord(char)
    for script, blocks in _SCRIPT_BLOCKS.items():
        if any(first <= code <= last for first, last in blocks):
            return script
    return None


def _dominant_script(text: str) -> str | None:
    counts: collections.Counter[str] = collections.Counter()
    letters = 0
    for char in text:
        if not unicodedata.category(char).startswith("L"):
            continue
        letters += 1
        script = _script_of(char)
        if script:
            counts[script] += 1
    if not letters or not counts:
        return None

    kana = counts.get("hiragana_katakana", 0)
    script, count = counts.most_common(1)[0]
    if kana and kana + counts.get("han", 0) >= letters * _NON_LATIN_SHARE:
        return "hiragana_katakana"
    if count >= letters * _NON_LATIN_SHARE:
        return script
    return None


def _score(tokens: list[str], candidates: list[str]) -> list[tuple[str, int]]:
    scored = [(code, sum(1 for token in tokens if token in _STOPWORDS[code])) for code in candidates]
    return sorted(scored, key=lambda item: -item[1])


def _decide(scored: list[tuple[str, int]], token_count: int) -> str | None:
    best_code, best_hits = scored[0]
    runner_up_hits = scored[1][1] if len(scored) > 1 else 0
    needed = MIN_HITS if token_count <= 6 else 3
    if best_hits < needed:
        return None
    if runner_up_hits and best_hits < runner_up_hits * 1.6:
        return None
    return best_code


def detect(text: str | None) -> str | None:
    """ISO 639-1 code of the language `text` is written in, or None when it is unclear."""
    if not text:
        return None

    script = _dominant_script(text)
    if script in _LANGUAGE_BY_SCRIPT:
        return _LANGUAGE_BY_SCRIPT[script]

    tokens = [token.lower() for token in _WORD.findall(text)]
    if len(tokens) < MIN_TOKENS:
        return None

    if script == "cyrillic":
        if any(char in _UKRAINIAN_ONLY for char in text.lower()):
            return "uk"
        return _decide(_score(tokens, ["ru", "uk"]), len(tokens))

    return _decide(_score(tokens, [code for code in _STOPWORDS if code not in ("ru", "uk")]), len(tokens))


def fits_language(text: str | None, language: str) -> bool:
    """False only when the text is recognisably another language than `language`."""
    detected = detect(text)
    return detected is None or detected == language
