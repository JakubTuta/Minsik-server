import sqlalchemy
import sqlalchemy.orm
import app.models.base


class Genre(app.models.base.Base):
    __tablename__ = "genres"
    __table_args__ = (
        sqlalchemy.Index("idx_genres_slug", "slug", unique=True),
        {"schema": "books"}
    )

    genre_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    name = sqlalchemy.Column(sqlalchemy.String(100), nullable=False)
    slug = sqlalchemy.Column(sqlalchemy.String(150), nullable=False, unique=True)

    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))

    books = sqlalchemy.orm.relationship("Book", secondary="books.book_genres", back_populates="genres")
