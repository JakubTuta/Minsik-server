import sqlalchemy
import sqlalchemy.orm
import app.models.base


class Comment(app.models.base.Base):
    __tablename__ = "comments"
    __table_args__ = (
        sqlalchemy.UniqueConstraint("user_id", "book_id", name="uq_comments_user_book"),
        {"schema": "user_data"},
    )

    comment_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    user_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False
    )
    book_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False
    )
    body: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Text, nullable=False
    )
    is_spoiler: sqlalchemy.orm.Mapped[bool] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false()
    )
    is_deleted: sqlalchemy.orm.Mapped[bool] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false()
    )
    created_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
    updated_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
