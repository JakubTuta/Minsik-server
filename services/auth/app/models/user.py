from sqlalchemy import Column, BigInteger, String, Boolean, Integer, Text, TIMESTAMP, text, CheckConstraint
from sqlalchemy.orm import relationship
import app.models.base


class User(app.models.base.Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="check_user_role"),
        {"schema": "auth"}
    )

    user_id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    username = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(200))
    password_hash = Column(String(255), nullable=False)
    role = Column(String(10), nullable=False, server_default="user")
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    avatar_url = Column(String(1000))
    bio = Column(Text)
    last_login = Column(TIMESTAMP)
    failed_login_attempts = Column(Integer, nullable=False, server_default=text("0"))
    locked_until = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
