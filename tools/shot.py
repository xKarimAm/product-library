"""Screenshot + probe the Product Library page. Harness only, never shipped."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js, shot

def main():
    url  = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7777/"
    size = sys.argv[2] if len(sys.argv) > 2 else "1600,1000"
    name = sys.argv[3] if len(sys.argv) > 3 else "now.png"
    extra = ["--force-prefers-reduced-motion"] if "--reduced" in sys.argv else None
    proc, ws = attach(url, size, extra)
    try:
        # Poll for the render instead of guessing a sleep. A cold scan of the
        # 60MB transcript corpus can take several seconds and a fixed wait
        # reported zero projects twice, which looked like a page fault.
        for _ in range(40):
            time.sleep(0.5)
            if js(ws, "typeof PROJECTS!=='undefined' && PROJECTS.length>0 "
                      "&& document.querySelectorAll('.node').length>0"):
                break
        time.sleep(1.2)
        print("errors     :", js(ws, "window.__err || 'none'"))
        print("projects   :", js(ws, "typeof PROJECTS!=='undefined'?PROJECTS.length:'NO PROJECTS'"))
        print("nodes      :", js(ws, "document.querySelectorAll('.node').length"))
        print("bots       :", js(ws, "document.querySelectorAll('.bot').length"))
        print("  trades   :", js(ws,
            "['farm','swim','build','fish','paint','read','eat','sleep'].map(c=>c+'='+document.querySelectorAll('.bot.'+c).length).join(' ')"))
        print("  all trades shown:", js(ws,
            "['farm','swim','build','fish','paint','read','eat'].every(c=>document.querySelectorAll('.bot.'+c).length>0)?'yes':'NO - a trade is missing'"))
        print("prism faces:", js(ws,
            "'roof='+document.querySelectorAll('#scene .mod').length"
            "+' wall='+document.querySelectorAll('#scene .modw').length"
            "+' flow='+document.querySelectorAll('#scene .flow').length"))
        print("SC / tally :", js(ws, "Math.round(SC*10)/10 + '  |  ' + document.getElementById('tally').textContent"))
        # THE truncation criterion. The old probe checked .chip and .pname; the
        # element that actually clips is .chip .nm, so it always said "none".
        print("TRUNCATED  :", js(ws,
            "[...document.querySelectorAll('.chip .nm')].filter(e=>e.scrollWidth>e.clientWidth+1)"
            ".map(e=>e.textContent.trim()).join(' | ') || 'none'"))
        # Tile overlap must be judged in WORLD space. Two diamonds that merely
        # share an edge still have overlapping screen bounding boxes, so a
        # getBoundingClientRect test would report false overlaps forever.
        print("TILE OVERLAP:", js(ws,
            "(()=>{let bad=[];for(let i=0;i<PROJECTS.length;i++)for(let j=i+1;j<PROJECTS.length;j++){"
            "const a=PROJECTS[i],b=PROJECTS[j];if(a._b!==b._b)continue;"
            "const dx=Math.abs(a._x0-b._x0),dy=Math.abs(a._y0-b._y0),w=a._w-1e-6;"
            "if(dx<w&&dy<w)bad.push(a.name+' / '+b.name);}"
            "return bad.length?bad.length+' OVERLAP: '+bad.slice(0,5).join(' | '):'none';})()"))
        print("bands      :", js(ws,
            "(()=>{const g={};PROJECTS.forEach(p=>{g[p._b]=(g[p._b]||0)+1});"
            "return 'active='+(g[0]||0)+' dormant='+(g[1]||0);})()"))
        print("chip clash :", js(ws,
            "(()=>{const ns=[...document.querySelectorAll('.chip')].map(n=>"
            "({k:n.textContent.trim().slice(0,16),r:n.getBoundingClientRect()}));"
            "let bad=[];for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){"
            "const a=ns[i].r,b=ns[j].r;"
            "if(a.right>b.left&&a.left<b.right&&a.bottom>b.top&&a.top<b.bottom)"
            "bad.push(ns[i].k+' / '+ns[j].k);}"
            "return bad.length?bad.length+': '+bad.slice(0,5).join(' | '):'none';})()"))
        print("offscreen  :", js(ws,
            "(()=>{let off=[];document.querySelectorAll('.node').forEach(n=>{const r=n.getBoundingClientRect();"
            "if(r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)off.push(n.textContent.trim().slice(0,14));});"
            "return off.length?off.join(' / '):'none';})()"))
        print("animations :", js(ws, "document.getAnimations().length"))
        shot(ws, name)
    finally:
        proc.terminate()

main()
