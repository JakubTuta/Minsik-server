import sqlalchemy
import app.db_base


class GenreCoOccurrence(app.db_base.Base):
    __tablename__ = "genre_co_occurrences"
    __table_args__ = (
        sqlalchemy.CheckConstraint("genre_id_a < genre_id_b", name="chk_genre_co_occ_order"),
        sqlalchemy.Index("idx_gco_a_strength", "genre_id_a", "strength"),
        sqlalchemy.Index("idx_gco_b_strength", "genre_id_b", "strength"),
        {"schema": "books"},
    )

    genre_id_a = sqlalchemy.Column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("books.genres.genre_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    genre_id_b = sqlalchemy.Column(
        sqlalchemy.BigInteger,
        sqlalchemy.ForeignKey("books.genres.genre_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    co_occurrence_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    strength = sqlalchemy.Column(sqlalchemy.Float, nullable=False)
    updated_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP(timezone=True), nullable=False, server_default=sqlalchemy.text("NOW()"))
