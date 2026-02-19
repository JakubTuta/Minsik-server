"""Add enhanced dump import columns to authors and books

Revision ID: 004
Revises: 003
Create Date: 2026-02-18

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "authors",
        sa.Column("wikidata_id", sa.String(50), nullable=True),
        schema="books",
    )
    op.add_column(
        "authors",
        sa.Column("wikipedia_url", sa.String(1000), nullable=True),
        schema="books",
    )
    op.add_column(
        "authors",
        sa.Column(
            "remote_ids", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        schema="books",
    )
    op.add_column(
        "authors",
        sa.Column(
            "alternate_names",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="books",
    )

    op.create_index(
        "idx_authors_open_library_id", "authors", ["open_library_id"], schema="books"
    )
    op.create_index(
        "idx_authors_wikidata_id", "authors", ["wikidata_id"], schema="books"
    )

    op.add_column(
        "books",
        sa.Column("isbn", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema="books",
    )
    op.add_column(
        "books", sa.Column("publisher", sa.String(500), nullable=True), schema="books"
    )
    op.add_column(
        "books", sa.Column("number_of_pages", sa.Integer, nullable=True), schema="books"
    )
    op.add_column(
        "books",
        sa.Column(
            "external_ids", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        schema="books",
    )
    op.add_column(
        "books",
        sa.Column(
            "ol_rating_count", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        schema="books",
    )
    op.add_column(
        "books",
        sa.Column("ol_avg_rating", sa.DECIMAL(3, 2), nullable=True),
        schema="books",
    )
    op.add_column(
        "books",
        sa.Column(
            "ol_want_to_read_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="books",
    )
    op.add_column(
        "books",
        sa.Column(
            "ol_currently_reading_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="books",
    )
    op.add_column(
        "books",
        sa.Column(
            "ol_already_read_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="books",
    )

    op.create_index(
        "idx_books_open_library_id", "books", ["open_library_id"], schema="books"
    )
    op.create_index(
        "idx_books_isbn", "books", ["isbn"], schema="books", postgresql_using="gin"
    )
    op.create_index(
        "idx_books_ol_rating_count",
        "books",
        [sa.text("ol_rating_count DESC")],
        schema="books",
    )
    op.create_index(
        "idx_books_ol_already_read_count",
        "books",
        [sa.text("ol_already_read_count DESC")],
        schema="books",
    )


def downgrade() -> None:
    op.drop_index("idx_books_ol_already_read_count", table_name="books", schema="books")
    op.drop_index("idx_books_ol_rating_count", table_name="books", schema="books")
    op.drop_index("idx_books_isbn", table_name="books", schema="books")
    op.drop_index("idx_books_open_library_id", table_name="books", schema="books")

    op.drop_column("books", "ol_already_read_count", schema="books")
    op.drop_column("books", "ol_currently_reading_count", schema="books")
    op.drop_column("books", "ol_want_to_read_count", schema="books")
    op.drop_column("books", "ol_avg_rating", schema="books")
    op.drop_column("books", "ol_rating_count", schema="books")
    op.drop_column("books", "external_ids", schema="books")
    op.drop_column("books", "number_of_pages", schema="books")
    op.drop_column("books", "publisher", schema="books")
    op.drop_column("books", "isbn", schema="books")

    op.drop_index("idx_authors_wikidata_id", table_name="authors", schema="books")
    op.drop_index("idx_authors_open_library_id", table_name="authors", schema="books")

    op.drop_column("authors", "alternate_names", schema="books")
    op.drop_column("authors", "remote_ids", schema="books")
    op.drop_column("authors", "wikipedia_url", schema="books")
    op.drop_column("authors", "wikidata_id", schema="books")
