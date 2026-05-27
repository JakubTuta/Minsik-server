import sqlalchemy
import app.models.base


class BookAuthor(app.models.base.Base):
    __tablename__ = "book_authors"
    __table_args__ = (
        sqlalchemy.UniqueConstraint("book_id", "author_id", name="uq_book_author"),
        sqlalchemy.Index("idx_book_authors_book_id", "book_id"),
        sqlalchemy.Index("idx_book_authors_author_id", "author_id"),
        {"schema": "books"}
    )

    book_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("books.books.book_id", ondelete="CASCADE"), primary_key=True)
    author_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("books.authors.author_id", ondelete="CASCADE"), primary_key=True)
