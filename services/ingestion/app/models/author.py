from sqlalchemy import Column, BigInteger, String, Integer, Text, Date, TIMESTAMP, Index, text
from sqlalchemy.orm import relationship
from app.models.base import Base


class Author(Base):
    __tablename__ = "authors"
    __table_args__ = (
        Index("idx_authors_slug", "slug", unique=True),
        Index("idx_authors_name", "name"),
        Index("idx_authors_view_count", "view_count", postgresql_ops={"view_count": "DESC"}),
        {"schema": "books"}
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

    view_count = Column(Integer, nullable=False, server_default=text("0"))
    last_viewed_at = Column(TIMESTAMP)

    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    open_library_id = Column(String(100))

    books = relationship("Book", secondary="books.book_authors", back_populates="authors")
