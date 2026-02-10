"""create auth schema

Revision ID: 001
Revises:
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS auth')

    op.execute("""
        CREATE TABLE IF NOT EXISTS auth.users (
            user_id             BIGSERIAL PRIMARY KEY,
            email               VARCHAR(255) NOT NULL UNIQUE,
            username            VARCHAR(100) NOT NULL UNIQUE,
            display_name        VARCHAR(200),
            password_hash       VARCHAR(255) NOT NULL,
            role                VARCHAR(10) NOT NULL DEFAULT 'user',
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            avatar_url          VARCHAR(1000),
            bio                 TEXT,
            last_login          TIMESTAMP,
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until        TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT check_user_role CHECK (role IN ('user', 'admin'))
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS auth.refresh_tokens (
            token_id            BIGSERIAL PRIMARY KEY,
            user_id             BIGINT NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,
            token_hash          VARCHAR(255) NOT NULL UNIQUE,
            expires_at          TIMESTAMP NOT NULL,
            is_revoked          BOOLEAN NOT NULL DEFAULT FALSE,
            revoked_at          TIMESTAMP,
            replaced_by_token_id BIGINT,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    op.create_index('idx_users_email', 'users', ['email'], schema='auth')
    op.create_index('idx_users_username', 'users', ['username'], schema='auth')
    op.create_index('idx_users_is_active', 'users', ['is_active'], schema='auth')
    op.create_index('idx_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], schema='auth')
    op.create_index('idx_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], schema='auth')
    op.create_index('idx_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'], schema='auth')

    op.execute("""
        CREATE OR REPLACE FUNCTION auth.update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trig_users_updated_at
            BEFORE UPDATE ON auth.users
            FOR EACH ROW
            EXECUTE FUNCTION auth.update_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_users_updated_at ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS auth.update_updated_at()")

    op.drop_index('idx_refresh_tokens_expires_at', table_name='refresh_tokens', schema='auth')
    op.drop_index('idx_refresh_tokens_user_id', table_name='refresh_tokens', schema='auth')
    op.drop_index('idx_refresh_tokens_token_hash', table_name='refresh_tokens', schema='auth')
    op.drop_index('idx_users_is_active', table_name='users', schema='auth')
    op.drop_index('idx_users_username', table_name='users', schema='auth')
    op.drop_index('idx_users_email', table_name='users', schema='auth')

    op.execute("DROP TABLE IF EXISTS auth.refresh_tokens")
    op.execute("DROP TABLE IF EXISTS auth.users")
    op.execute("DROP SCHEMA IF EXISTS auth")
