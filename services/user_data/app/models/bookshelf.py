import sqlalchemy
import sqlalchemy.orm
import app.models.base


class Bookshelf(app.models.base.Base):
    __tablename__ = "bookshelves"
    __table_args__ = (
        sqlalchemy.UniqueConstraint("user_id", "book_id", name="uq_bookshelves_user_book"),
        {"schema": "user_data"}
    )

    bookshelf_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    user_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False
    )
    book_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False
    )
    status: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column(
        sqlalchemy.String(20), nullable=False, server_default="want_to_read"
    )
    is_favorite: sqlalchemy.orm.Mapped[bool] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false()
    )
    created_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
    updated_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
