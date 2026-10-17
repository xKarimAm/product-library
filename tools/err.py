"""Trap page errors before any script runs, then read them back. Harness only."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach

TRAP = (
    "window.__err=[];"
    "window.addEventListener('error',function(e){"
    "window.__err.push((e.error&&(e.error.stack||e.error.message))||e.message);});"
    "window.addEventListener('unhandledrejection',function(e){"
    "window.__err.push('REJECT '+((e.reason&&(e.reason.stack||e.reason.message))||e.reason));});"
)

proc, ws = attach("about:blank", "1400,900")
try:
    ws.call("Page.addScriptToEvaluateOnNewDocument", source=TRAP)
    ws.call("Page.navigate", url="http://127.0.0.1:7777/")
    time.sleep(5.0)
    r = ws.call("Runtime.evaluate",
                expression="JSON.stringify(window.__err||['<trap missing>'])",
                returnByValue=True)
    val = r.get("result", {}).get("result", {}).get("value")
    errs = json.loads(val) if val else []
    if not errs:
        print("no page errors captured")
    for e in errs:
        print("-" * 60)
        print(e)
    r2 = ws.call("Runtime.evaluate",
                 expression="typeof PROJECTS!=='undefined'?PROJECTS.length:-1",
                 returnByValue=True)
    print("=" * 60)
    print("PROJECTS:", r2.get("result", {}).get("result", {}).get("value"))
finally:
    proc.terminate()
