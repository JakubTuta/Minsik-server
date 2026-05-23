from sqlalchemy import Column, BigInteger, Integer, Float, TIMESTAMP, ForeignKey, Index, CheckConstraint, text
from app.models.base import Base


class GenreCoOccurrence(Base):
    __tablename__ = "genre_co_occurrences"
    __table_args__ = (
        CheckConstraint("genre_id_a < genre_id_b", name="chk_genre_co_occ_order"),
        Index("idx_gco_a_strength", "genre_id_a", "strength"),
        Index("idx_gco_b_strength", "genre_id_b", "strength"),
        {"schema": "books"},
    )

    genre_id_a = Column(
        BigInteger,
        ForeignKey("books.genres.genre_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    genre_id_b = Column(
        BigInteger,
        ForeignKey("books.genres.genre_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    co_occurrence_count = Column(Integer, nullable=False)
    strength = Column(Float, nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
