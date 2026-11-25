"""Run the daily pipeline once from the command line (e.g. from Windows Task Scheduler or cron).

    python -m scripts.run_pipeline [--email you@example.com]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.models import User  # noqa: E402
from app.services.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="account email (default: first user)")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        q = db.query(User)
        user = q.filter(User.email == args.email.lower()).first() if args.email else q.order_by(User.id).first()
        if not user:
            sys.exit("No user found — create the owner account in the dashboard first.")
        run = run_pipeline(db, user, trigger="manual")
        print(json.dumps({"status": run.status, "error": run.error, "stats": run.stats}, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
