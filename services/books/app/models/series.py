import sqlalchemy
import sqlalchemy.orm
import app.models.base


class Series(app.models.base.Base):
    __tablename__ = "series"
    __table_args__ = (
        sqlalchemy.Index("idx_series_slug", "slug", unique=True),
        sqlalchemy.Index("idx_series_view_count", "view_count", postgresql_ops={"view_count": "DESC"}),
        {"schema": "books"}
    )

    series_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    name = sqlalchemy.Column(sqlalchemy.String(500), nullable=False)
    slug = sqlalchemy.Column(sqlalchemy.String(550), nullable=False, unique=True)
    description = sqlalchemy.Column(sqlalchemy.Text)
    total_books = sqlalchemy.Column(sqlalchemy.Integer)

    view_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))
    last_viewed_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP)

    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))
    updated_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))

    books = sqlalchemy.orm.relationship("Book", back_populates="series")
