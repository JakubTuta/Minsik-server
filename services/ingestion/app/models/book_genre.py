import sqlalchemy # Column, BigInteger, ForeignKey, Index, UniqueConstraint
from app.models.base import Base


class BookGenre(Base):
    __tablename__ = "book_genres"
    __table_args__ = (
        UniqueConstraint("book_id", "genre_id", name="uq_book_genre"),
        Index("idx_book_genres_book_id", "book_id"),
        Index("idx_book_genres_genre_id", "genre_id"),
        {"schema": "books"}
    )

    book_id = Column(BigInteger, ForeignKey("books.books.book_id", ondelete="CASCADE"), primary_key=True)
    genre_id = Column(BigInteger, ForeignKey("books.genres.genre_id", ondelete="CASCADE"), primary_key=True)
