"""
List which calculation functions in berdo/ the tests exercise:  python check_function_coverage.py
"""
import sys, ast, importlib, pathlib
sys.path.insert(0, ".")
called = set()
def tracer(frame, event, arg):
    if event == "call" and "/berdo/" in frame.f_code.co_filename:
        called.add((pathlib.Path(frame.f_code.co_filename).stem, frame.f_code.co_name))
sys.setprofile(tracer)
for p in sorted(pathlib.Path("tests").glob("test_*.py")):
    m = importlib.import_module(f"tests.{p.stem}")
    for n in dir(m):
        if n.startswith("test_"): getattr(m, n)()
sys.setprofile(None)
total = hit = 0
for mod in sorted(p.stem for p in pathlib.Path("berdo").glob("*.py") if p.stem not in ("__init__", "regulations", "schema")):
    t = ast.parse(open(f"berdo/{mod}.py").read())
    fns = [n.name for n in t.body if isinstance(n, ast.FunctionDef)]
    miss = [f for f in fns if (mod, f) not in called]
    total += len(fns); hit += len(fns) - len(miss)
    print(f"berdo/{mod}.py: {len(fns) - len(miss)} of {len(fns)}; not exercised: {miss}")
print(f"TOTAL: {hit} of {total} functions ({hit / total:.0%})")
