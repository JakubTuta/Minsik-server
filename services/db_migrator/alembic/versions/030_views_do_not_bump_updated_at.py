"""view counters no longer count as a change to the row

books.update_updated_at bumped updated_at whenever any column differed, and the view
counter flush rewrites view_count/last_viewed_at on every viewed row every few minutes.
updated_at feeds the incremental Elasticsearch sync and the sitemap's lastmod, so every
flush queued the most-viewed works for reindexing and stamped them "modified now".

The function is shared by books, authors and series. The WHEN guard on the triggers
still skips writes that change nothing at all; the function now also leaves updated_at
alone when only the counters moved. A write that sets updated_at itself is respected,
so a rename can mark the rows that display the old name without changing any of them.

Revision ID: 030
Revises: 029
Create Date: 2026-10-10
"""

from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION books.update_updated_at() RETURNS trigger AS $$
        BEGIN
            IF NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
                -- an explicit touch, e.g. an author rename marking that author's books
                -- for the search sync
                NULL;
            ELSIF (to_jsonb(NEW) - 'view_count' - 'last_viewed_at' - 'updated_at')
               IS DISTINCT FROM (to_jsonb(OLD) - 'view_count' - 'last_viewed_at' - 'updated_at') THEN
                NEW.updated_at = NOW();
            ELSE
                NEW.updated_at = OLD.updated_at;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION books.update_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
