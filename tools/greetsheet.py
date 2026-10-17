"""Renders every trade in its GREETING pose, scaled up. Harness only.

sheet.py cannot show this: a greeting needs a cursor, and .greet pins armA on and
armB off, so the wave is the one pose no other harness can put on screen. This is
what caught the .wav/armB collision being fixed rather than merely believed.

It also prints the rAF count for four mouse moves in NORMAL mode. phase3.py
--reduced asserts that count is 0; this is where the number that makes 0 mean
something comes from."""
import sys, os, time, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js

proc, ws = attach("http://127.0.0.1:7777/", "1600,1000")
try:
    for _ in range(60):
        time.sleep(0.5)
        if js(ws, "typeof VILLS!=='undefined' && VILLS.size>0 && "
                  "document.querySelectorAll('#scene .bot').length>0"):
            break
    time.sleep(1.0)
    js(ws, "clearInterval(TRAFFIC);if(typeof POLL!=='undefined')clearInterval(POLL);"
           "VILLS.forEach(v=>{v.trip=null;v.si=0;v.cool=1e12});layout()")
    time.sleep(0.5)

    # --- 1. the rAF counter, in NORMAL mode, where moves must schedule frames ---
    js(ws, "(()=>{window.__raf=0;const o=window.requestAnimationFrame;"
           "window.requestAnimationFrame=function(f){window.__raf++;"
           "return o.call(window,f);};})()")
    tgt = js(ws, "(()=>{const r=scene.getBoundingClientRect();let o=null;"
                 "VILLS.forEach(v=>{if(!o&&v.el&&v.el.isConnected&&!v.sleep)"
                 "o={x:r.left+v.sx,y:r.top+v.sy-(SPR_H-1.5)*(v.px||3),id:v.id};});"
                 "return o;})()")
    for dx, dy in ((0, 0), (3, 3), (-3, 0), (0, 5)):
        ws.call("Input.dispatchMouseEvent", type="mouseMoved",
                x=float(tgt["x"] + dx), y=float(tgt["y"] + dy),
                button="none", clickCount=0)
        time.sleep(0.14)
    print("NORMAL mode, rAF calls after 4 moves :", js(ws, "window.__raf"),
          "(reduced measured 0, so the counter discriminates)")
    print("that villager greeting               :",
          js(ws, "VILLS.get(" + repr(tgt["id"]).replace("'", '"')
                 + ").el.getAttribute('class')"))

    # --- 2. every trade, greeting, scaled up for a visual judgement ---
    trades = ["farm", "swim", "build", "fish", "paint", "read", "eat"]
    js(ws, """(()=>{
      const T=%s;
      const host=document.createElement('div');
      host.id='gshot';
      host.style.cssText='position:fixed;inset:0;z-index:9999;background:#241B2F;'
        +'display:flex;align-items:center;justify-content:center;gap:26px';
      const mk=(cls)=>{
        const s=document.createElementNS('http://www.w3.org/2000/svg','svg');
        s.setAttribute('width','150');s.setAttribute('height','190');
        s.setAttribute('viewBox','-2 -8 16 20');
        s.setAttribute('shape-rendering','crispEdges');
        const g=document.createElementNS('http://www.w3.org/2000/svg','g');
        g.setAttribute('class','bot '+cls+' greet');
        g.innerHTML=botBody(cls);
        s.appendChild(g);
        const w=document.createElement('div');
        w.style.cssText='text-align:center;color:#EDE6DA;font:600 13px system-ui';
        w.appendChild(s);
        const l=document.createElement('div');l.textContent=cls+' + greet';
        w.appendChild(l);
        return w;
      };
      T.forEach(t=>host.appendChild(mk(t)));
      document.body.appendChild(host);
    })()""" % str(trades).replace("'", '"'))
    time.sleep(1.2)
    d = ws.call("Page.captureScreenshot", format="png").get("result", {}).get("data")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "greet_trades.png")
    with open(out, "wb") as fh:
        fh.write(base64.b64decode(d))
    print("saved", out)
finally:
    proc.terminate()
