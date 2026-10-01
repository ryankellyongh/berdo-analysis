"""
Run the test suite without pytest:  python run_tests.py
(With pytest installed, `pytest` runs the same tests.)
"""
import importlib
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).parent))
failed = passed = 0
for path in sorted(pathlib.Path("tests").glob("test_*.py")):
    module = importlib.import_module(f"tests.{path.stem}")
    for name in sorted(n for n in dir(module) if n.startswith("test_")):
        try:
            getattr(module, name)()
            passed += 1
        except Exception:
            failed += 1
            print(f"FAIL {path.stem}.{name}")
            traceback.print_exc()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
