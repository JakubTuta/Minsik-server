from sqlalchemy import Column, BigInteger, String, Integer, Text, TIMESTAMP, DECIMAL, Index, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import relationship
from app.models.base import Base


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (
        Index("idx_series_slug", "slug", unique=True),
        Index("idx_series_ts_vector", "ts_vector", postgresql_using="gin"),
        Index("idx_series_view_count", "view_count", postgresql_ops={"view_count": "DESC"}),
        {"schema": "books"}
    )

    series_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False)
    slug = Column(String(550), nullable=False, unique=True)
    description = Column(Text)
    total_books = Column(Integer)

    ts_vector = Column(TSVECTOR)

    view_count = Column(Integer, nullable=False, server_default=text("0"))
    last_viewed_at = Column(TIMESTAMP)

    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    books = relationship("Book", back_populates="series")
