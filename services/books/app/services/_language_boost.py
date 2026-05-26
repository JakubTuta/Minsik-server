LANGUAGE_BOOST_WEIGHT = 100.0


def lang_boost_sql(column: str = "b.language", param: str = "language") -> str:
    return f"(CASE WHEN {column} = :{param} THEN {LANGUAGE_BOOST_WEIGHT} ELSE 1 END)"


def lang_boost_weight(book_language: str, user_language: str) -> float:
    return LANGUAGE_BOOST_WEIGHT if book_language == user_language else 1.0
