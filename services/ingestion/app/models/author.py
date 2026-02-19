from app.models.base import Base
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    Date,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship


class Author(Base):
    __tablename__ = "authors"
    __table_args__ = (
        Index("idx_authors_slug", "slug", unique=True),
        Index("idx_authors_name", "name"),
        Index(
            "idx_authors_view_count",
            "view_count",
            postgresql_ops={"view_count": "DESC"},
        ),
        Index("idx_authors_open_library_id", "open_library_id"),
        Index("idx_authors_wikidata_id", "wikidata_id"),
        {"schema": "books"},
    )

    author_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(300), nullable=False)
    slug = Column(String(350), nullable=False, unique=True)
    bio = Column(Text)
    birth_date = Column(Date)
    death_date = Column(Date)
    birth_place = Column(String(500))
    nationality = Column(String(200))
    photo_url = Column(String(1000))

    wikidata_id = Column(String(50))
    wikipedia_url = Column(String(1000))
    remote_ids = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    alternate_names = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    view_count = Column(Integer, nullable=False, server_default=text("0"))
    last_viewed_at = Column(TIMESTAMP)

    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    open_library_id = Column(String(100))

    books = relationship(
        "Book", secondary="books.book_authors", back_populates="authors"
    )
