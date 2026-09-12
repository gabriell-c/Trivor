import sys
sys.path.insert(0, '.')
try:
    import main
    print("MAIN OK", file=sys.stderr)
    print(f"app: {type(main.app)}", file=sys.stderr)
except Exception as e:
    print(f"MAIN FAIL: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
