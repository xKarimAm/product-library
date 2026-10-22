"""Eyeball a village mid-walk. Harness only.

The occlusion checks in phase2.py prove painter ORDER. They cannot prove the
route looks right - a villager can be correctly ordered and still be walking
through a roof it happens to be drawn in front of. So this forces traffic,
holds it mid-journey, and saves a wide shot plus a 2.4x zoom on the front-left
cluster for a human to look at.

Run:  py walkshot.py
Out:  walk_wide.png, walk_zoom.png, walk_front.png
"""
import sys, os, time, base64, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js

HERE = os.path.dirname(os.path.abspath(__file__))


def save(ws, name):
    d = ws.call("Page.captureScreenshot", format="png").get("result", {}).get("data")
    with open(os.path.join(HERE, name), "wb") as fh:
        fh.write(base64.b64decode(d))
    print("saved " + name)


proc, ws = attach("http://127.0.0.1:7777/", "1600,1000")
try:
    for _ in range(60):
        time.sleep(0.5)
        if js(ws, "typeof PROJECTS!=='undefined'&&PROJECTS.length>0"
                  "&&document.querySelectorAll('.bot').length>0") is True:
            break
    time.sleep(0.8)

    # Freeze the clock the loop reads, so travellers hold still at a chosen
    # point in their journey and the screenshot is not a blur of one instant.
    # Stopping the dispatcher too, or new trips keep starting under us.
    js(ws, "clearInterval(TRAFFIC)")
    js(ws, "VILLS.forEach(v=>{v.cool=0});for(let i=0;i<8;i++)dispatch()")
    print("travellers  :", js(ws, "[...VILLS.values()].filter(v=>v.trip).length"))
    # Hold until a messenger has actually ARRIVED at the front and is dwelling
    # (its step carries `hold`). A fixed sleep catches everyone still mid-route,
    # which is the one moment that cannot show whether the front reads right.
    # Keyed on the hold flag, never a step index: the trip used to be four
    # steps and is three now, so si==2 silently became the RETURN leg.
    for _ in range(40):
        time.sleep(0.5)
        if js(ws, "[...VILLS.values()].some(v=>v.trip&&v.kind==='msg'&&v.trip[v.si].hold)") is True:
            break
    print("in flight   :", js(ws, """JSON.stringify([...VILLS.values()]
        .filter(v=>v.trip).map(v=>({kind:v.kind,si:v.si,cls:v.cls,mode:v.mode})))"""))
    print("msg onscreen:", js(ws, """(()=>{const o=[...VILLS.values()]
        .filter(v=>v.trip&&v.kind==='msg').map(v=>{const r=v.el.getBoundingClientRect();
        return {id:v.id,si:v.si,top:Math.round(r.top),bottom:Math.round(r.bottom),
          inside:r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth};});
        return JSON.stringify(o);})()"""))
    # Park the loop where they stand: no more rAF, positions hold.
    js(ws, "cancelAnimationFrame(RAF);RAF=1e9")
    time.sleep(0.4)
    save(ws, "walk_wide.png")

    js(ws, "(()=>{const h=document.getElementById('hive');"
           "h.style.transformOrigin='30% 78%';h.style.transform='scale(2.4)';})()")
    time.sleep(0.5)
    save(ws, "walk_zoom.png")

    # And the front of the hive, where messengers stand waiting.
    js(ws, "(()=>{const h=document.getElementById('hive');"
           "h.style.transformOrigin='50% 96%';h.style.transform='scale(2.2)';})()")
    time.sleep(0.5)
    save(ws, "walk_front.png")
finally:
    proc.terminate()
