"""Is the messenger's pennant actually VISIBLE where it stands? Harness only.

The pennant is the only thing marking a messenger apart from a wanderer, and it
is drawn in #scene while the project labels live in #nodes, which is painted
after it on purpose (trap 9). So a messenger standing at the front of the hive -
directly below its own label - can have its pennant hidden by that label. That
is a measurement, not a guess: the first version flew the flag six pixels above
the head and was covered by the "Project Alpha" chip at 1600x1000.

Labels are fixed pixel sizes and their text is live data, so this has to be
checked at every width rather than derived once.

Run:  py msgcheck.py            (all four widths)
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js

SIZES = ["1600,1000", "1280,900", "1024,860", "820,940"]

PROBE = """(()=>{
  const out=[];
  [...VILLS.values()].filter(v=>v.trip&&v.kind==='msg'&&v.trip[v.si].hold).forEach(v=>{
    // The FLAG, not the whole pennant. The pole runs down toward the hand and
    // at narrow widths its lower half passes behind the label - but so does the
    // villager's own body, by 16-20px, even at REST. Labels outranking sprites
    // is trap 9 and predates all of this. What has to stay readable is the
    // amber signal that marks a messenger apart from a wanderer.
    const pen=v.el.querySelector('.flag');
    const p=pen.getBoundingClientRect(), s=v.el.getBoundingClientRect();
    let cover=[],clip=0;
    document.querySelectorAll('.node').forEach(n=>{
      const r=n.getBoundingClientRect();
      if(p.right>r.left&&p.left<r.right&&p.bottom>r.top&&p.top<r.bottom){
        cover.push(n.getAttribute('aria-label').split(',')[0]);
        clip=Math.max(clip,Math.round(Math.min(p.bottom,r.bottom)-Math.max(p.top,r.top)));
      }});
    out.push({id:v.id,covered:cover,clipPx:clip,
      penH:Math.round(p.height),
      feetToBottom:Math.round(innerHeight-s.bottom),
      onscreen:s.top>=0&&s.bottom<=innerHeight&&s.left>=0&&s.right<=innerWidth});
  });
  return JSON.stringify(out);})()"""

bad = []
for size in SIZES:
    proc, ws = attach("http://127.0.0.1:7777/", size)
    try:
        for _ in range(60):
            time.sleep(0.5)
            if js(ws, "typeof PROJECTS!=='undefined'&&PROJECTS.length>0"
                      "&&document.querySelectorAll('.bot').length>0") is True:
                break
        js(ws, "clearInterval(TRAFFIC)")
        # Make ONLY the waiting projects eligible, then dispatch. Zeroing every
        # cooldown instead leaves the weighted draw free to fill all four slots
        # with wanderers and no messenger ever leaves, which is how this check
        # returned "inconclusive" at 1600 while passing everywhere else.
        js(ws, """(()=>{VILLS.forEach(v=>{
             v.trip=null;v.si=0;v.wx=v.hx;v.wy=v.hy;v.wz=v.hz;
             const p=PROJECTS.find(q=>q.id===v.id);
             v.cool=(p&&p.waiting_count)?0:1e12;});
           for(let i=0;i<6;i++)dispatch();})()""")
        rows = []
        for i in range(60):
            time.sleep(0.4)
            got = js(ws, PROBE)
            rows = json.loads(got) if isinstance(got, str) and got[:1] == "[" else []
            if rows:
                break
            # Re-force periodically. A messenger's dwell is a 6s window inside a
            # ~10s round trip, so a single dispatch at the top can be missed if
            # the first draws all went to wanderers - which is how this reported
            # "inconclusive" at one width while measuring clean at every other.
            if i % 12 == 11:
                js(ws, """(()=>{VILLS.forEach(v=>{
                     v.trip=null;v.si=0;v.wx=v.hx;v.wy=v.hy;v.wz=v.hz;
                     const p=PROJECTS.find(q=>q.id===v.id);
                     v.cool=(p&&p.waiting_count)?0:1e12;});
                   for(let i=0;i<6;i++)dispatch();})()""")
        print("== " + size + "  SC=" + str(round(js(ws, "SC"), 1)))
        if not rows:
            print("   no messenger reached the front - INCONCLUSIVE")
            bad.append(size + " inconclusive")
            continue
        for r in rows:
            ok = not r["covered"] and r["onscreen"]
            print("   " + ("PASS " if ok else "FAIL ") + r["id"]
                  + "  pennant " + str(r["penH"]) + "px, clipped " + str(r["clipPx"]) + "px"
                  + ", covered by " + (str(r["covered"]) if r["covered"] else "nothing")
                  + ", feet " + str(r["feetToBottom"]) + "px above the viewport floor"
                  + ("" if r["onscreen"] else ", OFFSCREEN"))
            if not ok:
                bad.append(size + " " + r["id"] + " clip=" + str(r["clipPx"]))
    finally:
        proc.terminate()
        # Chrome needs a moment to release the debugging port before the
        # next size launches, or attach() fails on a live page.
        time.sleep(3.5)

print("")
print("pennant visible at every width" if not bad
      else "COVERED OR OFFSCREEN: " + " | ".join(bad))
sys.exit(1 if bad else 0)
