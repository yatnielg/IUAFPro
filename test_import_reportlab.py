import sys, platform
print("Python:", sys.version)
print("Arch  :", platform.architecture())
try:
    import reportlab
    print("reportlab:", getattr(reportlab, "__version__", "?"), reportlab.__file__)
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    print("OK: imports canvas y A4")
except Exception:
    import traceback; traceback.print_exc()
