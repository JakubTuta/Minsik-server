import sqlalchemy
import sqlalchemy.orm
import app.models.base


class UserStats(app.models.base.Base):
    __tablename__ = "user_stats"
    __table_args__ = {"schema": "user_data"}

    user_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    want_to_read_count: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer, nullable=False, server_default="0"
    )
    reading_count: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer, nullable=False, server_default="0"
    )
    read_count: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer, nullable=False, server_default="0"
    )
    abandoned_count: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer, nullable=False, server_default="0"
    )
    favourites_count: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer, nullable=False, server_default="0"
    )
    ratings_count: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer, nullable=False, server_default="0"
    )
    comments_count: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer, nullable=False, server_default="0"
    )
    created_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
    updated_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
