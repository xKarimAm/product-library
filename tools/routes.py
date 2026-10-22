"""Interaction + route check against the sample city. Harness only.

    py sample/make_sample.py --serve      # in another terminal, then:
    py tools/routes.py                    # exits 1 on any failed check
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js, shot

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # sheet text has arrows; cp1252 consoles choke
TARGET = "habit-tracker"          # a sample project with a checkpoint, a stale note and a gap
failed = []


def check(ok, what, got=None):
    print(("  PASS " if ok else "  FAIL ") + what + ("" if got is None else "   " + str(got)))
    if not ok:
        failed.append(what)


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
    if not until(ws, "typeof PROJECTS!=='undefined' && PROJECTS.length>0", 20):
        sys.exit("no city at 127.0.0.1:7777: is `py sample/make_sample.py --serve` running?")
    time.sleep(1.0)
    node = "document.querySelector('.node[data-id=\"'+CSS.escape(PROJECTS.find(x=>x.name==%r).id)+'\"]')" % TARGET

    print("-- click a cell --")
    check(js(ws, "(()=>{const n=%s;if(!n)return false;n.click();return true})()" % node), "click " + TARGET)
    until(ws, "!!document.getElementById('bubble')", 3)
    check(js(ws, "document.querySelector('#bubble h2')?.firstChild.textContent") == TARGET
          and js(ws, "!!document.querySelector('#bubble h2 .badge.stale')"), "bubble shows its name and STALE")
    check(js(ws, "(()=>{const r=document.getElementById('bubble').getBoundingClientRect();"
                 "return r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight})()"), "bubble fits on screen")
    # A label that is embedded must actually be inside its own cell.
    inside = js(ws,
        "(()=>{let bad=[];document.querySelectorAll('.node').forEach(n=>{"
        "const p=PROJECTS.find(x=>x.id===n.dataset.id);if(!p)return;"
        "const r=n.getBoundingClientRect();"
        "const hw=0.866*SC;"
        "const cellx=(p._x0-p._y0)*Math.cos(Math.PI/6)*SC+OX;"
        "if(r.left<cellx-hw-2||r.right>cellx+hw+2)bad.push(p.name.slice(0,18));});"
        "return bad.join(' | ')})()")
    check(not inside, "every label sits inside its cell", inside or None)
    js(ws, "window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
    check(until(ws, "!document.getElementById('bubble')", 3), "Esc closes the bubble")

    print("-- full view: focus goes in, the city is inert, focus comes back --")
    js(ws, "(()=>{const n=%s;n.focus();n.click()})()" % node)
    until(ws, "!!document.querySelector('#bubble button[data-act=\"full\"]')", 3)
    js(ws, "(()=>{const b=document.querySelector('#bubble button[data-act=\"full\"]');b.focus();b.click()})()")
    check(until(ws, "document.getElementById('sheet')?.getAttribute('aria-label')===%r" % TARGET), "full view opens")
    check(js(ws, "document.activeElement===document.getElementById('sheet')"), "focus moves into the sheet")
    check(js(ws, "[...hive.children].filter(c=>c.id!=='sheet').every(c=>c.inert)"), "the city behind the sheet is inert")
    sections = js(ws, "[...document.querySelectorAll('#sheet h3')].map(h=>h.textContent).join(' | ')")
    check("STALE STATE" in sections.upper() and "GATE" in sections.upper(), "sheet explains STALE and the gate", sections)
    js(ws, "window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
    check(until(ws, "location.pathname==='/' && !document.getElementById('sheet')", 3), "Esc closes the sheet")
    # The card stays open behind the sheet, so focus goes back to its Full view button.
    check(js(ws, "document.activeElement?.dataset.act==='full'"), "focus returns to the Full view button")
    check(js(ws, "![...hive.children].some(c=>c.inert)"), "the city is usable again")

    print("-- routes --")
    js(ws, "document.querySelector('.node').dataset.probe='keepme'")
    js(ws, "go('/p/'+encodeURIComponent(PROJECTS.find(p=>p.name===%r).id))" % TARGET)
    until(ws, "!!document.querySelector('#sheet h2')")
    js(ws, "history.back()")
    check(until(ws, "location.pathname==='/' && !document.getElementById('sheet')"), "Back returns to the city")
    check(js(ws, "document.querySelector('.node')?.dataset.probe==='keepme'"), "the canvas is kept, not rebuilt")
    # 1.6s was too short and `ul.flags li` is the wrong selector, so this
    # reported an empty /blocked twice while the route was working fine.
    js(ws, "go('/blocked')")
    until(ws, "!!document.querySelector('#sheet h2')")
    title = js(ws, "document.querySelector('#sheet h2')?.textContent") or ""
    check(title.endswith("waiting on you") and js(ws, "document.querySelectorAll('#sheet li').length") > 0,
          "/blocked lists what waits on you", title)
    for path, want in (("/plans", "Plans"), ("/report", "Report")):
        js(ws, "go(%r)" % path)
        check(until(ws, "document.querySelector('#sheet h2')?.textContent===%r" % want), path + " opens")
    js(ws, "go('/')")
    time.sleep(0.5)

    print("-- search --")
    js(ws, "(()=>{const s=document.getElementById('search');s.value='habit';"
           "s.dispatchEvent(new Event('input'));})()")
    time.sleep(0.5)
    hits = js(ws, "[...document.querySelectorAll('.node')].filter(n=>!n.classList.contains('dim'))"
                  ".map(n=>n.getAttribute('aria-label').split(',')[0])")
    check(hits == [TARGET], "search 'habit' finds only " + TARGET, hits)
    js(ws, "(()=>{const s=document.getElementById('search');s.value='';"
           "s.dispatchEvent(new Event('input'));})()")
    time.sleep(0.4)
    shot(ws, "hive_final_1600.png")
finally:
    proc.terminate()

print("\n" + ("all checks passed" if not failed else "%d FAILED: %s" % (len(failed), "; ".join(failed))))
sys.exit(1 if failed else 0)
