import sqlalchemy
import sqlalchemy.orm
import app.models.base


class User(app.models.base.Base):
    __tablename__ = "users"
    __table_args__ = (
        sqlalchemy.CheckConstraint("role IN ('user', 'admin')", name="check_user_role"),
        {"schema": "auth"}
    )

    user_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    email = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, unique=True)
    username = sqlalchemy.Column(sqlalchemy.String(100), nullable=False, unique=True)
    display_name = sqlalchemy.Column(sqlalchemy.String(200))
    google_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, unique=True)
    password_hash = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    role = sqlalchemy.Column(sqlalchemy.String(10), nullable=False, server_default="user")
    is_active = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.text("TRUE"))
    avatar_url = sqlalchemy.Column(sqlalchemy.String(1000))
    bio = sqlalchemy.Column(sqlalchemy.Text)
    last_login = sqlalchemy.Column(sqlalchemy.TIMESTAMP)
    failed_login_attempts = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, server_default=sqlalchemy.text("0"))
    locked_until = sqlalchemy.Column(sqlalchemy.TIMESTAMP)
    preferred_language = sqlalchemy.Column(sqlalchemy.String(8), nullable=False, server_default=sqlalchemy.text("'en'"))
    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))
    updated_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False, server_default=sqlalchemy.text("NOW()"))

    refresh_tokens = sqlalchemy.orm.relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
