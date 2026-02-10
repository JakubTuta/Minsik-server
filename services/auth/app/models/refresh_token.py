from sqlalchemy import Column, BigInteger, String, Boolean, TIMESTAMP, text, ForeignKey
from sqlalchemy.orm import relationship
import app.models.base


class RefreshToken(app.models.base.Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "auth"}

    token_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("auth.users.user_id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(TIMESTAMP, nullable=False)
    is_revoked = Column(Boolean, nullable=False, server_default=text("FALSE"))
    revoked_at = Column(TIMESTAMP)
    replaced_by_token_id = Column(BigInteger)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    user = relationship("User", back_populates="refresh_tokens")
