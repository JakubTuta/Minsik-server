import sqlalchemy
import sqlalchemy.orm
import app.db_base


class Series(app.db_base.Base):
    __tablename__ = "series"
    __table_args__ = (
        sqlalchemy.Index("idx_series_slug_language", "slug", "language", unique=True),
        sqlalchemy.Index("idx_series_view_count", "view_count", postgresql_ops={"view_count": "DESC"}),
        {"schema": "books"}
    )

    series_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    name = sqlalchemy.Column(sqlalchemy.String(500), nullable=False)
    slug = sqlalchemy.Column(sqlalchemy.String(550), nullable=False)
    language = sqlalchemy.Column(sqlalchemy.String(10), nullable=False)
    description = sqlalchemy.Column(sqlalchemy.Text)
    total_books = sqlalchemy.Column(sqlalchemy.Integer)

    view_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))
    last_viewed_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP)

    enrichment_attempted_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP(timezone=True))

    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))
    updated_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))

    books = sqlalchemy.orm.relationship("Book", back_populates="series")
