import sys, os, time, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js
HERE = os.path.dirname(os.path.abspath(__file__))
proc, ws = attach("http://127.0.0.1:7777/", "1600,1000")
try:
    for _ in range(40):
        time.sleep(0.5)
        if js(ws, "typeof PROJECTS!=='undefined' && document.querySelectorAll('.bot').length>0"):
            break
    time.sleep(1.0)
    # Scale up the whole hive around the front-left active cluster.
    js(ws, "(()=>{const s=document.getElementById('scene');"
           "const h=document.getElementById('hive');"
           "h.style.transformOrigin='30% 78%';h.style.transform='scale(2.4)';})()")
    time.sleep(0.6)
    data = ws.call("Page.captureScreenshot", format="png").get("result", {}).get("data")
    with open(os.path.join(HERE, "cell_zoom.png"), "wb") as fh:
        fh.write(base64.b64decode(data))
    print("saved cell_zoom.png")
finally:
    proc.terminate()
