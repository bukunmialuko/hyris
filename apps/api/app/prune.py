"""`python -m app.prune` -- delete aged-out checkpoints and quizzes.

A command rather than a background timer inside the API: when data disappears should be a scheduled,
visible operator decision, not a side effect of the server happening to be running.
"""

import logging
import sys

from sqlalchemy import create_engine

from app.services.persistence import sqlalchemy_dsn
from app.services.retention import prune


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    url = sqlalchemy_dsn()
    if not url:
        print("DATABASE_URL is unset or unusable; nothing to prune.", file=sys.stderr)
        return 1
    engine = create_engine(url)
    try:
        for table, n in prune(engine).items():
            print(f"{table}: {n}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
