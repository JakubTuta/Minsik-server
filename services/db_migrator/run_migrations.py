import logging
import os
import sys

from alembic import command
from alembic.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

ALEMBIC_DIR = os.path.join(os.path.dirname(__file__), "alembic")


def main() -> None:
    logger.info("Starting database migrations")
    cfg = Config()
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    command.upgrade(cfg, "head")
    logger.info("All migrations completed successfully")


if __name__ == "__main__":
    main()
