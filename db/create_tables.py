

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.models import Base  # noqa: E402
from db.session import engine  # noqa: E402


def main() -> None:
    Base.metadata.create_all(engine)
    print("All tables created (or already existed).")


if __name__ == "__main__":
    main()
