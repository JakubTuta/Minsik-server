PLACEHOLDER_TITLES = ["untitled", "unknown", "no title", "n/a", "tbd", "test"]

NAME_JUNK_CHARS = " \t\r\n,;:|/\\=*^<>-–—·•"

JUNK_PUBLISHER_NAME_PATTERN = (
    r"\m(publishing|publishers|press|editions|verlag|editorial)\M\s*$"
)

COLLECTION_NAME_PATTERN = (
    r"(\momnibus\M"
    r"|\mbox(ed)?[ -]?sets?\M"
    r"|\mboxsets?\M"
    r"|\mbind[ -]?up\M"
    r"|\mcomplete (works|novels|stories|series|collection|edition|adventures)\M"
    r"|\mcollected (works|novels|stories|poems|edition)\M"
    r"|\manthology\M"
    r"|\mcompendium\M"
    r"|\mtreasury\M"
    r"|\m\d+[ -]?in[ -]?1\M"
    r"|\m\d+[ -]book (set|bundle|collection|series)\M"
    r"|\m(books?|vols?|volumes?|parts?)[ ]?\d+[ ]?[-–—/&][ ]?\d+"
    # Anchored to the end: mid-title it is a series descriptor
    # ("Star Wars - Thrawn Trilogy - Heir to the Empire" is one novel).
    r"|\m((tri|tetra|penta|hexa)logy|duology|quartet)[\s.,:;!-]*$)"
)

NON_BOOK_TITLE_PATTERN = (
    r"\[(sound recording|audio recording|microform|microfiche|electronic resource"
    r"|videorecording|videocassette|braille|kit|filmstrip|slide|cd-rom|dvd)\]"
)

COLLECTIVE_AUTHOR_PATTERN = (
    r"^\s*(various( authors| artists| contributors)?|anonymous|anon\.?"
    r"|unknown( author)?|no author|not available|n\.?/?a\.?"
    r"|collectif|collective|diverse|verschiedene( autoren)?|autori vari|varios autores"
    r"|vv\.? ?aa\.?|aa\.? ?vv\.?|staff|editors?|editorial staff|the editors( of .*)?"
    r"|compiled by.*|edited by.*|et al\.?)\s*$"
)

# "&" and "and" are not merge markers: real names and organisations use them
# ("Arkady and Boris Strugatsky", "Gilbert & George", "Health & Safety Executive").
MERGED_AUTHOR_ENTRY_PATTERN = r"(\met al\M|;)"

JUNK_GENRE_NAME_PATTERN = (
    r"(accessible book|protected daisy|in library|internet archive|overdrive"
    r"|print[ -]disabled|lending library|reading level|staff picks|large type"
    r"|open library|\mtexts\M|\mnyt\M|new york times)"
)

OL_ENGAGEMENT_SQL = """(
    COALESCE(b.ol_rating_count, 0)
    + COALESCE(b.ol_want_to_read_count, 0)
    + COALESCE(b.ol_currently_reading_count, 0)
    + COALESCE(b.ol_already_read_count, 0)
)"""

BOOK_UNTOUCHED_BY_USERS_SQL = """(
    b.rating_count = 0
    AND NOT EXISTS (SELECT 1 FROM user_data.bookshelves ub WHERE ub.book_id = b.book_id)
    AND NOT EXISTS (SELECT 1 FROM user_data.ratings ur WHERE ur.book_id = b.book_id)
    AND NOT EXISTS (SELECT 1 FROM user_data.comments uc WHERE uc.book_id = b.book_id)
)"""

# view_count counts raw GetBook hits (crawlers included), so it is not an
# engagement signal: only rows a Minsik user touched are protected.
BOOK_DELETABLE_SQL = (
    """(
    b.created_at < NOW() - INTERVAL '1 day'
    AND """
    + BOOK_UNTOUCHED_BY_USERS_SQL
    + ")"
)

QUALITY_SCORE_SQL = """(
    (CASE WHEN b.description IS NOT NULL AND b.description != '' THEN 1 ELSE 0 END) +
    (CASE WHEN b.primary_cover_url IS NOT NULL THEN 1 ELSE 0 END) +
    (CASE WHEN EXISTS (SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id) THEN 1 ELSE 0 END) +
    (CASE WHEN EXISTS (SELECT 1 FROM books.book_genres bg WHERE bg.book_id = b.book_id) THEN 1 ELSE 0 END) +
    (CASE WHEN b.original_publication_year IS NOT NULL THEN 1 ELSE 0 END) +
    (CASE WHEN b.isbn IS NOT NULL AND b.isbn != '[]'::jsonb THEN 1 ELSE 0 END) +
    (CASE WHEN b.number_of_pages IS NOT NULL AND b.number_of_pages > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN b.publisher IS NOT NULL AND b.publisher != '' THEN 1 ELSE 0 END)
)"""

LOW_QUALITY_BOOK_SQL = (
    """(
    (
      """
    + QUALITY_SCORE_SQL
    + """ < :min_score
      AND (b.rating_count + COALESCE(b.ol_rating_count, 0)) < :engagement
      AND (
        COALESCE(b.ol_already_read_count, 0)
        + (SELECT COUNT(*) FROM user_data.bookshelves bs WHERE bs.book_id = b.book_id)
      ) < :engagement
      AND (
        COALESCE(b.ol_want_to_read_count, 0)
        + COALESCE(b.ol_currently_reading_count, 0)
      ) < :engagement
    )
    OR NOT EXISTS (SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id)
    OR b.title ~ '^[\\s\\W]*$'
    OR char_length(btrim(b.title)) < 2
    OR char_length(b.title) > :max_title_length
    OR b.title ~ '^[0-9\\s[:punct:]]+$'
    OR b.title ~* '(https?://|www\\.)'
    OR b.title ~* :non_book_pattern
    OR lower(btrim(b.title)) = ANY(:placeholder_titles)
    OR b.language !~ '^[a-z]{2,3}(-[A-Za-z0-9]{1,8})?$'
    OR (
      COALESCE(b.ol_rating_count, 0) >= :ol_min_rating_count
      AND b.ol_avg_rating < :ol_min_avg_rating
    )
    OR b.original_publication_year > EXTRACT(YEAR FROM NOW())::int + 1
    OR b.original_publication_year < :min_year
    OR (
      NOT EXISTS (SELECT 1 FROM books.book_genres bg WHERE bg.book_id = b.book_id)
      AND """
    + QUALITY_SCORE_SQL
    + """ < 5
    )
)"""
)

LOW_ENGAGEMENT_BOOK_SQL = OL_ENGAGEMENT_SQL + " < :min_engagement"

def outside_parentheses(column: str) -> str:
    """A parenthesised tail is a series descriptor, not a collection marker:
    "Daughter of the Blood (The Black Jewels Trilogy, Book 1)" is one novel."""
    return f"regexp_replace({column}, '\\([^)]*\\)', ' ', 'g')"


COLLECTION_BOOK_SQL = outside_parentheses("b.title") + " ~* :collection_pattern"

MULTI_AUTHOR_BOOK_SQL = (
    "(SELECT COUNT(*) FROM books.book_authors ba WHERE ba.book_id = b.book_id)"
    " >= :max_authors"
)

AUTHOR_DELETABLE_SQL = """(
    a.created_at < NOW() - INTERVAL '1 day'
    AND NOT EXISTS (
        SELECT 1 FROM books.book_authors ba
        JOIN books.books b ON b.book_id = ba.book_id
        WHERE ba.author_id = a.author_id AND NOT """ + BOOK_UNTOUCHED_BY_USERS_SQL + """
    )
)"""

AUTHOR_JUNK_NAME_SQL = r"""(
    a.name !~ '[A-Za-z]'
    OR char_length(btrim(a.name)) < 2
    OR char_length(a.name) > 120
    OR array_length(regexp_split_to_array(btrim(a.name), '\s+'), 1) > 8
)"""

COLLECTIVE_AUTHOR_SQL = (
    "(a.name ~* :collective_pattern OR a.name ~* :merged_entry_pattern)"
)

LOW_ENGAGEMENT_AUTHOR_SQL = (
    """COALESCE((
    SELECT SUM("""
    + OL_ENGAGEMENT_SQL
    + """)
    FROM books.book_authors ba
    JOIN books.books b ON b.book_id = ba.book_id
    WHERE ba.author_id = a.author_id
), 0) < :min_engagement"""
)

SERIES_DELETABLE_SQL = """(
    s.view_count <= 2
    AND NOT EXISTS (
        SELECT 1 FROM books.books b
        WHERE b.series_id = s.series_id AND NOT """ + BOOK_UNTOUCHED_BY_USERS_SQL + """
    )
)"""

LOW_ENGAGEMENT_SERIES_SQL = (
    """COALESCE((
    SELECT SUM("""
    + OL_ENGAGEMENT_SQL
    + """)
    FROM books.books b
    WHERE b.series_id = s.series_id
), 0) < :min_engagement"""
)
