from sqlalchemy import Column, BigInteger, String, Integer, Text, DECIMAL, TIMESTAMP, Index, text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.base import Base


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (
        Index("idx_books_language", "language"),
        Index("idx_books_ts_vector", "ts_vector", postgresql_using="gin"),
        Index("idx_books_language_slug", "language", "slug", unique=True),
        Index("idx_books_rating_count", "rating_count", postgresql_ops={"rating_count": "DESC"}),
        Index("idx_books_view_count", "view_count", postgresql_ops={"view_count": "DESC"}),
        {"schema": "books"}
    )

    book_id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    language = Column(String(10), nullable=False)
    slug = Column(String(600), nullable=False)
    description = Column(Text)
    original_publication_year = Column(Integer)

    formats = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    cover_history = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    primary_cover_url = Column(String(1000))

    ts_vector = Column(TSVECTOR)

    rating_count = Column(Integer, nullable=False, server_default=text("0"))
    avg_rating = Column(DECIMAL(3, 2))
    sub_rating_stats = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    view_count = Column(Integer, nullable=False, server_default=text("0"))
    last_viewed_at = Column(TIMESTAMP)

    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    open_library_id = Column(String(100))
    google_books_id = Column(String(100))

    series_id = Column(BigInteger, ForeignKey("books.series.series_id"))
    series_position = Column(DECIMAL(5, 2))

    authors = relationship("Author", secondary="books.book_authors", back_populates="books")
    genres = relationship("Genre", secondary="books.book_genres", back_populates="books")
    series = relationship("Series", back_populates="books")
