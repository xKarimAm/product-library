"""Interaction + route check against the hive DOM. Harness only."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js, shot


def until(ws, expr, secs=15):
    """Poll for a condition instead of sleeping a guessed interval.

    Every 'broken route' this harness has ever reported was this: a fixed sleep
    shorter than the render. It happened twice before and again on 2026-09-13,
    when a cold scan after a server restart made /p/ and /blocked look empty
    while both were fine. A sheet that has not rendered yet is not a failure.
    """
    for _ in range(int(secs * 4)):
        v = js(ws, expr)
        if v:
            return v
        time.sleep(0.25)
    return None

proc, ws = attach("http://127.0.0.1:7777/", "1600,1000")
try:
    for _ in range(40):
        time.sleep(0.5)
        if js(ws, "typeof PROJECTS!=='undefined' && PROJECTS.length>0"):
            break
    time.sleep(1.0)

    print("-- click a cell --")
    print("click Project Alpha  :", js(ws,
        "(()=>{const p=PROJECTS.find(x=>x.name==='Project Alpha');if(!p)return 'not found';"
        "const n=document.querySelector('.node[data-id=\"'+CSS.escape(p.id)+'\"]');"
        "if(!n)return 'no chip';n.click();return 'clicked';})()"))
    time.sleep(0.8)
    print("bubble present  :", js(ws, "!!document.getElementById('bubble')"))
    print("bubble heading  :", js(ws, "document.querySelector('#bubble h2')?.textContent"))
    print("bubble fits     :", js(ws,
        "(()=>{const b=document.getElementById('bubble');if(!b)return 'none';"
        "const r=b.getBoundingClientRect();"
        "return 'fits='+(r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight);})()"))
    print("roof colours    :", js(ws,
        "(()=>{const m={};document.querySelectorAll('#scene .hut').forEach(h=>{"
        "const c=h.style.getPropertyValue('--roof')||'?';m[c]=(m[c]||0)+1;});"
        "return Object.entries(m).map(([k,v])=>k+' x'+v).join('  ');})()"))
    print("cells drawn     :", js(ws,
        "'cell-t='+document.querySelectorAll('#scene .cell-t').length"
        "+' vacant='+document.querySelectorAll('#scene .plaque.vacant').length"
        "+' rim='+document.querySelectorAll('#scene .cell-rim').length"))
    # A label that is embedded must actually be inside its own cell.
    print("label in cell   :", js(ws,
        "(()=>{let bad=[];document.querySelectorAll('.node').forEach(n=>{"
        "const p=PROJECTS.find(x=>x.id===n.dataset.id);if(!p)return;"
        "const r=n.getBoundingClientRect();"
        "const cxp=p._chipX,hw=0.866*SC,hh=0.58*SC;"
        "const cellx=(p._x0-p._y0)*Math.cos(Math.PI/6)*SC+OX;"
        "if(r.left<cellx-hw-2||r.right>cellx+hw+2)bad.push(p.name.slice(0,18));});"
        "return bad.length?bad.length+' wider than cell: '+bad.slice(0,5).join(' | '):'all inside';})()"))

    js(ws, "window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
    time.sleep(0.4)
    print("Esc closed      :", js(ws, "!document.getElementById('bubble')"))

    print("")
    print("-- routes --")
    js(ws, "document.querySelector('.node').dataset.probe='keepme'")
    js(ws, "go('/p/'+encodeURIComponent(PROJECTS.find(p=>p.name==='Project Alpha').id))")
    until(ws, "!!document.querySelector('#sheet h2')")
    print("sheet title     :", js(ws, "document.querySelector('#sheet h2')?.textContent"))
    print("sections        :", js(ws, "[...document.querySelectorAll('#sheet h3')].map(h=>h.textContent).join(' | ')"))
    js(ws, "history.back()")
    until(ws, "location.pathname==='/' && !document.getElementById('sheet')")
    print("back url        :", js(ws, "location.pathname"))
    print("canvas kept     :", js(ws, "document.querySelector('.node')?.dataset.probe==='keepme'"))
    # 1.6s was too short and `ul.flags li` is the wrong selector, so this
    # reported an empty /blocked twice while the route was working fine.
    js(ws, "go('/blocked')")
    until(ws, "!!document.querySelector('#sheet h2')")
    print("blocked title   :", js(ws, "document.querySelector('#sheet h2')?.textContent"))
    print("blocked items   :", js(ws, "document.querySelectorAll('#sheet li').length"))
    js(ws, "go('/plans')")
    until(ws, "!!document.querySelector('#sheet h2')")
    print("plans title     :", js(ws, "document.querySelector('#sheet h2')?.textContent"))
    js(ws, "go('/')")
    time.sleep(0.8)

    print("")
    print("-- search --")
    js(ws, "(()=>{const s=document.getElementById('search');s.value='zeta';"
           "s.dispatchEvent(new Event('input'));})()")
    time.sleep(0.5)
    print("'zeta' hits :", js(ws,
        "[...document.querySelectorAll('.node')].filter(n=>!n.classList.contains('dim'))"
        ".map(n=>n.textContent.trim().slice(0,20)).join(' / ')"))
    js(ws, "(()=>{const s=document.getElementById('search');s.value='';"
           "s.dispatchEvent(new Event('input'));})()")
    time.sleep(0.4)
    shot(ws, "hive_final_1600.png")
finally:
    proc.terminate()
