import sqlalchemy
import sqlalchemy.orm
import app.models.base


class RefreshToken(app.models.base.Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "auth"}

    token_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("auth.users.user_id", ondelete="CASCADE"), nullable=False)
    token_hash = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, unique=True)
    expires_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False)
    is_revoked = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.text("FALSE"))
    revoked_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP)
    replaced_by_token_id = sqlalchemy.Column(sqlalchemy.BigInteger)
    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))

    user = sqlalchemy.orm.relationship("User", back_populates="refresh_tokens")
