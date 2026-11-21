"""Run the test suite with pytest (pip install -r requirements-dev.txt)."""
import sys

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["tests", *sys.argv[1:]]))
