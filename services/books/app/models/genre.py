from sqlalchemy import Column, BigInteger, String, TIMESTAMP, Index, text
from sqlalchemy.orm import relationship
from app.models.base import Base


class Genre(Base):
    __tablename__ = "genres"
    __table_args__ = (
        Index("idx_genres_slug", "slug", unique=True),
        {"schema": "books"}
    )

    genre_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(150), nullable=False, unique=True)

    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    books = relationship("Book", secondary="books.book_genres", back_populates="genres")
