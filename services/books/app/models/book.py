import datetime

import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.orm
import app.db_base


class Book(app.db_base.Base):
    __tablename__ = "books"
    __table_args__ = (
        sqlalchemy.Index("idx_books_language", "language"),
        sqlalchemy.Index("idx_books_language_slug", "language", "slug", unique=True),
        sqlalchemy.Index(
            "idx_books_rating_count",
            "rating_count",
            postgresql_ops={"rating_count": "DESC"},
        ),
        sqlalchemy.Index(
            "idx_books_view_count", "view_count", postgresql_ops={"view_count": "DESC"}
        ),
        sqlalchemy.Index("idx_books_open_library_id", "open_library_id"),
        sqlalchemy.Index("idx_books_isbn", "isbn", postgresql_using="gin"),
        sqlalchemy.Index(
            "idx_books_ol_rating_count",
            "ol_rating_count",
            postgresql_ops={"ol_rating_count": "DESC"},
        ),
        sqlalchemy.Index(
            "idx_books_ol_already_read_count",
            "ol_already_read_count",
            postgresql_ops={"ol_already_read_count": "DESC"},
        ),
        {"schema": "books"},
    )

    book_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    title = sqlalchemy.Column(sqlalchemy.String(500), nullable=False)
    language = sqlalchemy.Column(sqlalchemy.String(10), nullable=False)
    slug = sqlalchemy.Column(sqlalchemy.String(600), nullable=False)
    description = sqlalchemy.Column(sqlalchemy.Text)
    first_sentence = sqlalchemy.Column(sqlalchemy.Text)
    original_publication_year = sqlalchemy.Column(sqlalchemy.Integer)

    formats = sqlalchemy.Column(sqlalchemy.dialects.postgresql.JSONB, nullable=False, server_default=sqlalchemy.text("'[]'::jsonb"))
    primary_cover_url = sqlalchemy.Column(sqlalchemy.String(1000))

    isbn = sqlalchemy.Column(sqlalchemy.dialects.postgresql.JSONB, nullable=False, server_default=sqlalchemy.text("'[]'::jsonb"))
    publisher = sqlalchemy.Column(sqlalchemy.String(500))
    number_of_pages = sqlalchemy.Column(sqlalchemy.Integer)
    external_ids = sqlalchemy.Column(sqlalchemy.dialects.postgresql.JSONB, nullable=False, server_default=sqlalchemy.text("'{}'::jsonb"))

    rating_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))
    avg_rating = sqlalchemy.Column(sqlalchemy.DECIMAL(3, 2))
    sub_rating_stats = sqlalchemy.Column(sqlalchemy.dialects.postgresql.JSONB, nullable=False, server_default=sqlalchemy.text("'{}'::jsonb"))
    rating_distribution = sqlalchemy.Column(
        sqlalchemy.dialects.postgresql.JSONB, nullable=False, server_default=sqlalchemy.text("'{}'::jsonb")
    )

    ol_rating_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))
    ol_avg_rating = sqlalchemy.Column(sqlalchemy.DECIMAL(3, 2))
    ol_want_to_read_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))
    ol_currently_reading_count = sqlalchemy.Column(
        sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0")
    )
    ol_already_read_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))

    view_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))
    last_viewed_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP)

    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))
    updated_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))

    open_library_id = sqlalchemy.Column(sqlalchemy.String(100))
    google_books_id = sqlalchemy.Column(sqlalchemy.String(100))

    series_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("books.series.series_id"))
    series_position = sqlalchemy.Column(sqlalchemy.DECIMAL(5, 2))

    authors = sqlalchemy.orm.relationship(
        "Author", secondary="books.book_authors", back_populates="books"
    )
    genres = sqlalchemy.orm.relationship(
        "Genre", secondary="books.book_genres", back_populates="books"
    )
    series = sqlalchemy.orm.relationship("Series", back_populates="books")
