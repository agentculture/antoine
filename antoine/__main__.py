"""Allow running antoine as ``python -m antoine``."""

import sys

from antoine.cli import main

if __name__ == "__main__":
    sys.exit(main())
