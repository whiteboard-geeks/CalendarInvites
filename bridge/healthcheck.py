"""Container probe: DB/schema and durable worker heartbeat, without secret output."""
import sys
from .config import Settings
from .store import Store


def main():
    try:
        return 0 if Store(Settings.load().database_url).ready() else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
