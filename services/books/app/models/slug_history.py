import sqlalchemy
import app.db_base


class SlugHistory(app.db_base.Base):
    """A slug an entity used to have, so links to it keep working after a rename."""

    __tablename__ = "slug_history"
    __table_args__ = {"schema": "books"}

    entity_type = sqlalchemy.Column(sqlalchemy.String(10), primary_key=True)
    language = sqlalchemy.Column(sqlalchemy.String(10), primary_key=True, server_default=sqlalchemy.text("''"))
    old_slug = sqlalchemy.Column(sqlalchemy.String(600), primary_key=True)
    entity_id = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP(timezone=True), nullable=False, server_default=sqlalchemy.text("NOW()"))
