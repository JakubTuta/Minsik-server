import typing
import sqlalchemy
import sqlalchemy.orm
import app.models.base


class Rating(app.models.base.Base):
    __tablename__ = "ratings"
    __table_args__ = (
        sqlalchemy.UniqueConstraint("user_id", "book_id", name="uq_ratings_user_book"),
        {"schema": "user_data"}
    )

    rating_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    user_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False
    )
    book_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False
    )
    overall_rating: sqlalchemy.orm.Mapped[float] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Numeric(2, 1), nullable=False
    )
    review_text: sqlalchemy.orm.Mapped[typing.Optional[str]] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Text, nullable=True
    )
    pacing: sqlalchemy.orm.Mapped[typing.Optional[float]] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Numeric(2, 1), nullable=True
    )
    emotional_impact: sqlalchemy.orm.Mapped[typing.Optional[float]] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Numeric(2, 1), nullable=True
    )
    intellectual_depth: sqlalchemy.orm.Mapped[typing.Optional[float]] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Numeric(2, 1), nullable=True
    )
    writing_quality: sqlalchemy.orm.Mapped[typing.Optional[float]] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Numeric(2, 1), nullable=True
    )
    rereadability: sqlalchemy.orm.Mapped[typing.Optional[float]] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Numeric(2, 1), nullable=True
    )
    created_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
    updated_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
