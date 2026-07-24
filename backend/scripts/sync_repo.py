import argparse

from app.db import Base, SessionLocal, engine
from app.sync import sync_repo


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally sync a GitHub repo's PRs and reviews")
    parser.add_argument("owner")
    parser.add_argument("repo")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        synced = sync_repo(db, args.owner, args.repo)
        print(f"Synced {synced} pull requests for {args.owner}/{args.repo}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
