import sqlalchemy
import app.db_base


class BookGenre(app.db_base.Base):
    __tablename__ = "book_genres"
    __table_args__ = (
        sqlalchemy.UniqueConstraint("book_id", "genre_id", name="uq_book_genre"),
        sqlalchemy.Index("idx_book_genres_book_id", "book_id"),
        sqlalchemy.Index("idx_book_genres_genre_id", "genre_id"),
        {"schema": "books"}
    )

    book_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("books.books.book_id", ondelete="CASCADE"), primary_key=True)
    genre_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("books.genres.genre_id", ondelete="CASCADE"), primary_key=True)
