LANGUAGE_BOOST_WEIGHT = 100.0


def lang_boost_weight(book_language: str, user_language: str) -> float:
    return LANGUAGE_BOOST_WEIGHT if book_language == user_language else 1.0
