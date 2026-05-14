"""Allow running seer as ``python -m seer``."""

import sys

from seer.cli import main

if __name__ == "__main__":
    sys.exit(main())
