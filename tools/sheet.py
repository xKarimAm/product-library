"""One frame with every trade scaled up, both arm phases. Harness only.
Updated 2026-09-10: villagers are SVG scene content now, so each sample needs
its own <svg> host rather than being an HTML div."""
import sys, os, time, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js
HERE = os.path.dirname(os.path.abspath(__file__))

proc, ws = attach("http://127.0.0.1:7777/", "1500,900")
try:
    for _ in range(40):
        time.sleep(0.5)
        if js(ws, "typeof botNode==='function' && typeof PROJECTS!=='undefined' && PROJECTS.length>0"):
            break
    time.sleep(1.0)
    print("built:", js(ws, r"""
      (()=>{
        const NS='http://www.w3.org/2000/svg';
        // The last three are Phase 2's travel looks, not trades: what a
        // messenger, a courier and a wanderer carry while walking.
        const acts=['farm','swim','build','fish','paint','read','eat','sleep',
                    'flag','carry','plain'];
        const wrap=document.createElement('div');
        wrap.id='__sheet'; wrap.style.cssText=
          'position:fixed;inset:0;background:#241436;z-index:99999;'+
          'display:flex;flex-wrap:wrap;align-content:flex-start;gap:34px;padding:70px 40px';
        acts.forEach(m=>{
          const cell=document.createElement('div');
          cell.style.cssText='width:150px;height:230px;position:relative;text-align:center';
          const svg=document.createElementNS(NS,'svg');
          svg.setAttribute('width','150'); svg.setAttribute('height','180');
          svg.style.cssText='position:absolute;left:0;top:0;overflow:visible';
          svg.appendChild(botNode(75,150,m,{mode:m,px:7}));
          const lab=document.createElement('div');
          lab.textContent=m; lab.style.cssText='position:absolute;bottom:0;left:0;right:0;'+
            'color:#fff;font:600 15px system-ui';
          cell.appendChild(svg); cell.appendChild(lab); wrap.appendChild(cell);
        });
        document.body.appendChild(wrap);
        return acts.length+' samples';
      })()
    """))
    time.sleep(0.8)
    data = ws.call("Page.captureScreenshot", format="png").get("result", {}).get("data")
    with open(os.path.join(HERE, "sheet_a.png"), "wb") as fh:
        fh.write(base64.b64decode(data))
    print("saved sheet_a.png (natural phase)")
    js(ws, "document.querySelectorAll('#__sheet .armA').forEach(a=>a.style.opacity='0');"
           "document.querySelectorAll('#__sheet .armB').forEach(a=>a.style.opacity='1');")
    time.sleep(0.4)
    data = ws.call("Page.captureScreenshot", format="png").get("result", {}).get("data")
    with open(os.path.join(HERE, "sheet_b.png"), "wb") as fh:
        fh.write(base64.b64decode(data))
    print("saved sheet_b.png (armB forced)")
finally:
    proc.terminate()
