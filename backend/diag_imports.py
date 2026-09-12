import sys
sys.path.insert(0, '.')

try:
    import docling
    print("docling OK")
except Exception as e:
    print(f"docling FAIL: {e}")

try:
    import pypdfium2
    print("pypdfium2 OK")
except Exception as e:
    print(f"pypdfium2 FAIL: {e}")

try:
    import export_utils
    print("export_utils OK")
except Exception as e:
    print(f"export_utils FAIL: {e}")

try:
    import market_export
    print("market_export OK")
except Exception as e:
    print(f"market_export FAIL: {e}")

try:
    import logging_service
    print("logging_service OK")
except Exception as e:
    print(f"logging_service FAIL: {e}")

try:
    import main
    print("main import OK")
except Exception as e:
    print(f"main FAIL: {e}")
    import traceback
    traceback.print_exc()
