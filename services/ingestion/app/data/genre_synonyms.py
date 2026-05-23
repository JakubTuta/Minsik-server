import re

GENRE_SYNONYMS: dict[str, str] = {
    # Science fiction variants
    "sci-fi": "science-fiction",
    "scifi": "science-fiction",
    "sf": "science-fiction",
    "science-fiction-fantasy": "science-fiction",
    "science-fiction-and-fantasy": "science-fiction",
    "speculative-fiction": "science-fiction",
    # Fantasy variants
    "high-fantasy": "fantasy",
    "epic-fantasy": "fantasy",
    "dark-fantasy": "fantasy",
    "heroic-fantasy": "fantasy",
    "sword-and-sorcery": "fantasy",
    # Young adult variants
    "ya": "young-adult",
    "y-a": "young-adult",
    "ya-fiction": "young-adult",
    "young-adults": "young-adult",
    "teen": "young-adult",
    "teenage": "young-adult",
    "young-adult-fiction": "young-adult",
    # Mystery/thriller variants
    "mysteries": "mystery",
    "mystery-fiction": "mystery",
    "detective-fiction": "mystery",
    "detective-stories": "mystery",
    "whodunit": "mystery",
    "crime-fiction": "crime",
    "crime-thriller": "crime",
    "thrillers": "thriller",
    "thriller-fiction": "thriller",
    "suspense-fiction": "thriller",
    # Romance variants
    "romantic-fiction": "romance",
    "love-stories": "romance",
    "romantic-suspense": "romance",
    # Horror variants
    "horror-fiction": "horror",
    "ghost-stories": "horror",
    "supernatural-fiction": "horror",
    # Historical variants
    "historical-fiction": "historical",
    "historical-novels": "historical",
    "history-fiction": "historical",
    # Literary fiction variants
    "literary-fiction": "fiction",
    "general-fiction": "fiction",
    "mainstream-fiction": "fiction",
    # Nonfiction variants
    "non-fiction": "nonfiction",
    "nonfiction-books": "nonfiction",
    # Biography variants
    "biographies": "biography",
    "autobiographies": "autobiography",
    "memoirs": "memoir",
    # Self-help variants
    "self-improvement": "self-help",
    "personal-development": "self-help",
    "personal-growth": "self-help",
    # Short stories variants
    "short-story": "short-stories",
    "short-fiction": "short-stories",
    "flash-fiction": "short-stories",
    # Graphic novels variants
    "comic-books": "graphic-novels",
    "comics": "graphic-novels",
    "manga": "graphic-novels",
    # Classic variants
    "classics": "classic",
    "classic-literature": "classic",
    "classical-literature": "classic",
    # Adventure variants
    "adventure-stories": "adventure",
    "action-adventure": "adventure",
    # Children's variants
    "childrens": "children",
    "childrens-fiction": "children",
    "juvenile-fiction": "children",
    "juvenile-literature": "children",
    "picture-books": "children",
    # Poetry variants
    "poems": "poetry",
    "verse": "poetry",
    # Drama variants
    "plays": "drama",
    "theater": "drama",
    # Philosophy variants
    "philosophical-fiction": "philosophy",
    # Humor variants
    "humorous-fiction": "humor",
    "comedy": "humor",
    "satire": "humor",
    # Dystopia/utopia
    "dystopian-fiction": "dystopia",
    "utopian-fiction": "dystopia",
    "post-apocalyptic-fiction": "dystopia",
}

GENRE_NOISE_PATTERNS: list[str] = [
    r"\s*--\s*fiction$",
    r"\s*\(genre\)$",
    r"^fiction,\s*",
    r"\s+in\s+english$",
    r"\s+literature$",
    r"\s*-\s*fiction$",
    r"^american\s+",
    r"^english\s+",
    r"^british\s+",
    r"\s+novels?$",
    r"\s+stories?$",
    r"\s+books?$",
]

_COMPILED_NOISE: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in GENRE_NOISE_PATTERNS
]


def strip_genre_noise(name: str) -> str:
    for pattern in _COMPILED_NOISE:
        name = pattern.sub("", name)
    return name.strip()
