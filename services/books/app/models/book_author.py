from sqlalchemy import Column, BigInteger, ForeignKey, Index, UniqueConstraint
from app.models.base import Base


class BookAuthor(Base):
    __tablename__ = "book_authors"
    __table_args__ = (
        UniqueConstraint("book_id", "author_id", name="uq_book_author"),
        Index("idx_book_authors_book_id", "book_id"),
        Index("idx_book_authors_author_id", "author_id"),
        {"schema": "books"}
    )

    book_id = Column(BigInteger, ForeignKey("books.books.book_id", ondelete="CASCADE"), primary_key=True)
    author_id = Column(BigInteger, ForeignKey("books.authors.author_id", ondelete="CASCADE"), primary_key=True)
