import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.orm
import app.models.base


class Author(app.models.base.Base):
    __tablename__ = "authors"
    __table_args__ = (
        sqlalchemy.Index("idx_authors_slug", "slug", unique=True),
        sqlalchemy.Index("idx_authors_name", "name"),
        sqlalchemy.Index(
            "idx_authors_view_count",
            "view_count",
            postgresql_ops={"view_count": "DESC"},
        ),
        sqlalchemy.Index("idx_authors_open_library_id", "open_library_id"),
        sqlalchemy.Index("idx_authors_wikidata_id", "wikidata_id"),
        {"schema": "books"},
    )

    author_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    name = sqlalchemy.Column(sqlalchemy.String(300), nullable=False)
    slug = sqlalchemy.Column(sqlalchemy.String(350), nullable=False, unique=True)
    bio = sqlalchemy.Column(sqlalchemy.Text)
    birth_date = sqlalchemy.Column(sqlalchemy.Date)
    death_date = sqlalchemy.Column(sqlalchemy.Date)
    birth_place = sqlalchemy.Column(sqlalchemy.String(500))
    nationality = sqlalchemy.Column(sqlalchemy.String(200))
    photo_url = sqlalchemy.Column(sqlalchemy.String(1000))

    wikidata_id = sqlalchemy.Column(sqlalchemy.String(50))
    wikipedia_url = sqlalchemy.Column(sqlalchemy.String(1000))
    remote_ids = sqlalchemy.Column(sqlalchemy.dialects.postgresql.JSONB, nullable=False, server_default=sqlalchemy.text("'{}'::jsonb"))
    alternate_names = sqlalchemy.Column(sqlalchemy.dialects.postgresql.JSONB, nullable=False, server_default=sqlalchemy.text("'[]'::jsonb"))

    view_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))
    last_viewed_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP)

    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))
    updated_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))

    open_library_id = sqlalchemy.Column(sqlalchemy.String(100))

    books = sqlalchemy.orm.relationship(
        "Book", secondary="books.book_authors", back_populates="authors"
    )
