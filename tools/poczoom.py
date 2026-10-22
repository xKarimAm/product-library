"""Zoom the POC city so the skyline can be judged by eye, not by shot.py's
pass/fail lines. Renders a magnified crop around the active comb.

  py tools/poczoom.py [scale] [out.png]
"""
import sys, os, time, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "file:///" + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "poc_city.html").replace("\\", "/")
SCALE = sys.argv[1] if len(sys.argv) > 1 else "2.1"
OUT = sys.argv[2] if len(sys.argv) > 2 else "poc_zoom.png"

proc, ws = attach(URL, "1600,1000")
try:
    for _ in range(60):
        time.sleep(0.5)
        if js(ws, "typeof VILLS!=='undefined' && VILLS.size>0 && "
                  "document.querySelectorAll('#scene .bot').length>0"):
            break
    time.sleep(1.2)
    # Stop both intervals (trap 18) so the scene holds still for the capture.
    js(ws, "clearInterval(TRAFFIC);if(typeof POLL!=='undefined')clearInterval(POLL);")
    # Magnify around the front-left of the live comb, where the towers with
    # cranes are. transform-origin in percent keeps it stable across widths.
    js(ws, "(()=>{const s=document.getElementById('scene');"
           "s.style.transformOrigin='22% 74%';s.style.transform='scale(" + SCALE + ")';"
           "const n=document.getElementById('nodes');"
           "if(n){n.style.transformOrigin='22% 74%';n.style.transform='scale(" + SCALE + ")';}})()")
    time.sleep(0.8)
    d = ws.call("Page.captureScreenshot", format="png").get("result", {}).get("data")
    with open(os.path.join(HERE, OUT), "wb") as fh:
        fh.write(base64.b64decode(d))
    print("saved", OUT, "at scale", SCALE)
finally:
    proc.terminate()
