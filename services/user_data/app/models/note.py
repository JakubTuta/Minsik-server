import typing
import sqlalchemy
import sqlalchemy.orm
import app.models.base


class Note(app.models.base.Base):
    __tablename__ = "notes"
    __table_args__ = {"schema": "user_data"}

    note_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, primary_key=True
    )
    user_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False
    )
    book_id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(
        sqlalchemy.BigInteger, nullable=False
    )
    note_text: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Text, nullable=False
    )
    page_number: sqlalchemy.orm.Mapped[typing.Optional[int]] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Integer, nullable=True
    )
    is_spoiler: sqlalchemy.orm.Mapped[bool] = sqlalchemy.orm.mapped_column(
        sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.false()
    )
    created_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
    updated_at: sqlalchemy.orm.Mapped[sqlalchemy.DateTime] = sqlalchemy.orm.mapped_column(
        sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()
    )
