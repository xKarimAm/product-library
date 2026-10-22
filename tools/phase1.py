"""Phase 1 acceptance: villagers are scene content, still not click targets,
and correctly ordered for occlusion. Harness only."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js

proc, ws = attach("http://127.0.0.1:7777/", "1600,1000")
try:
    for _ in range(40):
        time.sleep(0.5)
        if js(ws, "typeof PROJECTS!=='undefined' && document.querySelectorAll('#scene .bot').length>0"):
            break
    time.sleep(1.0)

    # Phase 2 added traffic, and "every villager immediately after its own cell"
    # is a RESTING invariant - a villager mid-journey is slotted by depth
    # instead, on purpose. This suite happened to keep passing only because it
    # runs inside the 3s grace before the dispatcher starts, which is a race, not
    # a test. So park the village first: no trips, nobody eligible to leave,
    # everyone re-homed. Then the invariant means what it says whenever this runs.
    if js(ws, "typeof VILLS!=='undefined'") is True:
        # POLL too, not just TRAFFIC: the unnamed 30s `load` interval used to be
        # unstoppable, so a run outlasting it had every villager node rebuilt
        # mid-assertion. Guarded by typeof for builds from before POLL was named.
        js(ws, "clearInterval(TRAFFIC);if(typeof POLL!=='undefined')clearInterval(POLL);"
               "VILLS.forEach(v=>{v.trip=null;v.si=0;"
               "v.cool=1e12});layout()")
        time.sleep(0.4)

    print("villagers in scene :", js(ws, "document.querySelectorAll('#scene .bot').length"))
    print("villagers in HTML  :", js(ws,
        "document.querySelectorAll('#bots').length + ' #bots divs (want 0)'"))

    # 1. Not a click target. This protects the launcher.
    print("pointer-events     :", js(ws,
        "(()=>{const bad=[...document.querySelectorAll('#scene .bot')]"
        ".filter(b=>getComputedStyle(b).pointerEvents!=='none');"
        "return bad.length?bad.length+' villagers ARE clickable (bug)':'none clickable, correct';})()"))

    # 2. The real proof: what does the cursor actually hit over a villager?
    print("hit test over bot  :", js(ws,
        "(()=>{const out=[];document.querySelectorAll('#scene .bot').forEach(b=>{"
        "const r=b.getBoundingClientRect();"
        "const cx=Math.round(r.left+r.width/2),cy=Math.round(r.top+r.height/2);"
        "const hit=document.elementFromPoint(cx,cy);"
        "if(!hit){out.push('nothing');return;}"
        "const pl=hit.closest?hit.closest('.plaque'):null;"
        "out.push(pl?('cell:'+(pl.dataset.id===b.dataset.id?'own':'other')):('NON-CELL:'+hit.tagName));});"
        "const g={};out.forEach(v=>g[v]=(g[v]||0)+1);"
        "return Object.entries(g).map(([k,v])=>k+' x'+v).join('  ');})()"))

    # 3. Occlusion ordering: a villager must sit AFTER its own cell in the
    #    scene's child list, and before any nearer cell.
    print("depth ordering     :", js(ws,
        "(()=>{const kids=[...document.getElementById('scene').children];"
        "let bad=[];document.querySelectorAll('#scene .bot').forEach(b=>{"
        "const id=b.dataset.id;"
        "const cell=kids.find(k=>k.classList&&k.classList.contains('plaque')&&k.dataset.id===id);"
        "if(!cell){bad.push('no cell for '+id);return;}"
        "const bi=kids.indexOf(b),ci=kids.indexOf(cell);"
        "if(bi!==ci+1)bad.push(id+' bot@'+bi+' cell@'+ci);});"
        "return bad.length?bad.length+' misordered: '+bad.slice(0,3).join(' | ')"
        ":'every villager immediately after its own cell';})()"))

    # 4. A far villager must be painted before (under) a nearer cell.
    print("occluded by nearer :", js(ws,
        "(()=>{const kids=[...document.getElementById('scene').children];"
        "const bots=[...document.querySelectorAll('#scene .bot')];"
        "let ok=0,bad=0;bots.forEach(b=>{const p=PROJECTS.find(x=>x.id===b.dataset.id);if(!p)return;"
        "const bd=p._x0+p._y0,bi=kids.indexOf(b);"
        "PROJECTS.concat([]).forEach(q=>{const qd=q._x0+q._y0;"
        "const qc=kids.find(k=>k.classList&&k.classList.contains('plaque')&&k.dataset.id===q.id);"
        "if(!qc||q.id===p.id)return;"
        "const qi=kids.indexOf(qc);"
        "if(qd>bd){ if(qi>bi) ok++; else bad++; }});});"
        "return 'nearer-cell-after-villager ok='+ok+' violations='+bad;})()"))

    # 5. Search must fade a villager with its cell.
    js(ws, "(()=>{const s=document.getElementById('search');s.value='zeta';"
           "s.dispatchEvent(new Event('input'));})()")
    time.sleep(0.5)
    print("search fades bots  :", js(ws,
        "(()=>{const b=[...document.querySelectorAll('#scene .bot')];"
        "const dim=b.filter(x=>parseFloat(getComputedStyle(x).opacity)<0.5).length;"
        "return dim+' of '+b.length+' villagers dimmed (want most)';})()"))
    js(ws, "(()=>{const s=document.getElementById('search');s.value='';"
           "s.dispatchEvent(new Event('input'));})()")
    time.sleep(0.4)

    # 6. The launcher path: clicking a cell still opens the bubble.
    print("cell click works   :", js(ws,
        "(()=>{const p=PROJECTS.find(x=>x.name==='Project Alpha');"
        "const n=document.querySelector('.node[data-id=\"'+CSS.escape(p.id)+'\"]');"
        "n.click();return 'clicked';})()"))
    time.sleep(0.8)
    print("bubble opened      :", js(ws,
        "document.querySelector('#bubble h2')?.textContent || 'NO BUBBLE'"))
finally:
    proc.terminate()
