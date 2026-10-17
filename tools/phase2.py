"""Phase 2 acceptance: villager traffic. Harness only, ships with nothing.

Every assertion here exists because the spec named it, and each one is checked
by MEASURING the page rather than by reading the source:

  - the four-traveller cap holds under forced scheduling
  - a traveller's element really does move in the scene tree as its depth
    crosses a cell's, and lands between the right pair of cells (occlusion)
  - a journey survives layout() - the 30s poll - and a resize, without teleport
  - sleepers never leave home
  - all three traffic kinds actually dispatch
  - a cell click still opens the bubble while villagers are mid-walk
  - everyone gets home, back into the Phase 1 slot, and the loop idles out
  - with --reduced: the loop never starts and nobody ever walks

Run:  py phase2.py            (normal)
      py phase2.py --reduced  (prefers-reduced-motion)
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js

URL = "http://127.0.0.1:7777/"
FAILS = []


def check(label, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + label + ("  " + str(detail) if detail else ""))
    if not ok:
        FAILS.append(label)


def ready(ws):
    """Poll for the render. A cold scan of the corpus takes seconds, so a fixed
    sleep here is the documented way to report an empty page (trap 15)."""
    for _ in range(60):
        time.sleep(0.5)
        if js(ws, "typeof PROJECTS!=='undefined'&&PROJECTS.length>0"
                  "&&document.querySelectorAll('.bot').length>0") is True:
            # Stop the 30s `load` poll the moment the page is usable. This suite
            # runs well past 30s, and a poll landing mid-assertion calls layout(),
            # which re-runs place()/fit() and replaces every villager node - so a
            # traveller measured before it and judged after it is compared against
            # a comb that has since moved. That is how "no traveller ever stood
            # outside a cell" failed once on 2026-09-13 and passed on the very next
            # run with nothing changed in between. Guarded by typeof so this still
            # works against a build from before POLL was given a name.
            js(ws, "if(typeof POLL!=='undefined')clearInterval(POLL)")
            return True
    return False


# Forced scheduling: clear cooldowns and dispatch. Poking VILLS directly is
# deliberate - waiting out the real 9-18s cooldowns would make the suite useless.
def force(n):
    return ("(()=>{VILLS.forEach(v=>{v.cool=0});"
            "for(let i=0;i<" + str(n) + ";i++)dispatch();"
            "return [...VILLS.values()].filter(v=>v.trip).length;})()")

# The occlusion proof, for every traveller in flight, and it asserts the SAME
# property phase1.py:60 asserts for villagers at rest, just against a live
# position: a cell in a NEARER row must be painted after the villager, and one
# in a farther row before it.
#
# Cells in the villager's own row are a deliberate don't-care, exactly as in
# Phase 1 where the test is `qd > bd` and every same-row cell ties. A row is
# 2*B_STEP = 1.74 deep, so "another row" means a depth gap over half of that.
# The first version of this check demanded the villager sit after EVERY cell
# inside its biased bucket, which same-row cells are - and it failed 177 times
# on correct output, including for villagers standing still at home. A harness
# that fails on the state Phase 1 already proved good is wrong before the code is.
PROOF = """(()=>{
  const kids=[...scene.children];
  const out=[];
  [...VILLS.values()].filter(v=>v.trip).forEach(v=>{
    const d=v.wx+v.wy, vi=kids.indexOf(v.el);
    let nearerBefore=0, fartherAfter=0, ok=0;
    CELLD.forEach((cd,i)=>{
      const ci=kids.indexOf(CELLG[i]);
      if(cd>d+0.87){ if(ci>vi) ok++; else nearerBefore++; }
      else if(cd<d-0.87){ if(ci<vi) ok++; else fartherAfter++; }
    });
    out.push({id:v.id,kind:v.kind,si:v.si,cls:v.cls,vi:vi,
      b:CELLD.filter(x=>x<=d+0.87).length,bk:v.bucket,
      ok:nearerBefore===0&&fartherAfter===0,pairs:ok,
      nearerBefore:nearerBefore,fartherAfter:fartherAfter});
  });
  return JSON.stringify(out);})()"""

STATE = """(()=>JSON.stringify([...VILLS.values()].map(v=>({
  id:v.id,kind:v.kind||null,trip:!!v.trip,si:v.si,sleep:!!v.sleep,cls:v.cls,
  wx:+v.wx.toFixed(4),wy:+v.wy.toFixed(4),wz:+v.wz.toFixed(4),
  tf:v.el.style.transform,bucket:v.bucket}))))()"""


def by_id(rows):
    return {r["id"]: r for r in rows}


def main():
    reduced = "--reduced" in sys.argv
    extra = ["--force-prefers-reduced-motion"] if reduced else None
    proc, ws = attach(URL, "1600,1000", extra)
    try:
        if not ready(ws):
            print("page never rendered")
            return 1
        print("mode              : " + ("REDUCED MOTION" if reduced else "normal"))
        print("villagers         : " + str(js(ws, "VILLS.size")))
        print("cells in table    : " + str(js(ws, "CELLG.length")) + " groups, "
              + str(js(ws, "CELLD.length")) + " depths")

        if reduced:
            print("")
            print("-- reduced motion: the loop must never start --")
            check("media query is live", js(ws, "RM.matches") is True)
            js(ws, force(40))
            time.sleep(2.5)
            check("no trips dispatched",
                  js(ws, "[...VILLS.values()].filter(v=>v.trip).length") == 0)
            check("rAF never started", js(ws, "RAF") == 0)
            check("no walking sprite",
                  js(ws, "document.querySelectorAll('.bot.walk,.bot.wait').length") == 0)
            check("everyone at home", js(ws,
                  "[...VILLS.values()].every(v=>v.wx===v.hx&&v.wy===v.hy&&v.wz===v.hz)") is True)
            check("no looping CSS animation on a bot", js(ws,
                  "[...document.querySelectorAll('.bot,.bot *')]"
                  ".filter(n=>getComputedStyle(n).animationName!=='none'"
                  "&&getComputedStyle(n).animationIterationCount!=='1').length") == 0)
            print("")
            print("REDUCED: " + ("all checks passed" if not FAILS
                                 else str(len(FAILS)) + " FAILED"))
            return 1 if FAILS else 0

        home = by_id(json.loads(js(ws, STATE)))
        sleepers = [k for k, v in home.items() if v["sleep"]]
        print("sleepers          : " + str(len(sleepers)))

        print("")
        print("-- the four-traveller cap, under forced scheduling --")
        peak, seen_kinds = 0, set()
        for _ in range(8):
            n = js(ws, force(12))
            check("dispatch returned a count", isinstance(n, int), n)
            peak = max(peak, n if isinstance(n, int) else 0)
            for k in json.loads(js(ws,
                    "JSON.stringify([...VILLS.values()].filter(v=>v.trip).map(v=>v.kind))")):
                seen_kinds.add(k)
            time.sleep(0.25)
        check("cap of 4 holds", peak <= 4, "peak simultaneous travellers = " + str(peak))
        check("at least one traveller", peak >= 1, "peak = " + str(peak))

        print("")
        print("-- occlusion: element position in the scene tree, sampled in flight --")
        buckets, proofs, bad = {}, 0, []
        for _ in range(60):
            rows = json.loads(js(ws, PROOF))
            for r in rows:
                proofs += 1
                if r["kind"]:
                    seen_kinds.add(r["kind"])
                buckets.setdefault(r["id"], set()).add(r["b"])
                if not r["ok"]:
                    bad.append(r)
            js(ws, "VILLS.forEach(v=>{v.cool=0});dispatch()")
            time.sleep(0.22)
        moved = {k: sorted(v) for k, v in buckets.items() if len(v) > 1}
        check("every in-flight sample correctly ordered",
              not bad, str(proofs) + " samples, " + str(len(bad)) + " violations"
              + ("  e.g. " + json.dumps(bad[0]) if bad else ""))
        # Natural traffic no longer crosses a row: wanderers visit same-row
        # neighbours and a messenger now steps forward inside its OWN cell, so
        # nothing changes depth bucket on its own. The re-insertion path still
        # has to be proven, so drive a villager across a row boundary by hand
        # and assert both the bucket number and the DOM slot move with it.
        cross = json.loads(js(ws, """(()=>{
          const v=[...VILLS.values()].find(x=>!x.sleep&&!x.trip);
          const kids=()=>[...scene.children].indexOf(v.el);
          const at=(d)=>{v.wx=v.hx+d/2;v.wy=v.hy+d/2;paint(v);
            return {b:v.bucket,i:kids()};};
          const back=at(-1.74), home=at(0), fwd=at(1.74);
          v.wx=v.hx;v.wy=v.hy;v.wz=v.hz;paint(v);v.cellG.after(v.el);
          v.bucket=bucketOf(v.wx+v.wy);
          return JSON.stringify({id:v.id,back:back,home:home,fwd:fwd});})()"""))
        check("driving a villager one row back moves its bucket and DOM slot",
              cross["back"]["b"] < cross["home"]["b"]
              and cross["back"]["i"] < cross["home"]["i"], cross["back"])
        check("driving it one row forward moves them the other way",
              cross["fwd"]["b"] > cross["home"]["b"]
              and cross["fwd"]["i"] > cross["home"]["i"], cross["fwd"])
        if moved:
            print("  (natural traffic also crossed: " + json.dumps(moved)[:120] + ")")
        check("re-insertion tracked the bucket", js(ws,
              "[...VILLS.values()].filter(v=>v.trip)"
              ".every(v=>v.bucket===CELLD.filter(x=>x<=v.wx+v.wy+0.87).length)") is True)

        print("")
        print("-- all three traffic kinds dispatch --")
        for k in ("msg", "wander"):
            check("kind " + k + " seen in free running", k in seen_kinds, sorted(seen_kinds))
        # The courier is ONE candidate against a dozen, so whether it happens to
        # win a weighted draw inside the sampling window is luck - an earlier run
        # saw it and the next did not. Its logic is what matters, so assert that
        # deterministically: the edge it walks must be recent[1] -> recent[0],
        # "where you came from" to "where you are now".
        edge = json.loads(js(ws, """(()=>{
          const act=PROJECTS.filter(p=>p._t!==3&&p.path_exists);
          const recent=act.slice().sort((a,b)=>
            new Date(b.last_activity||0)-new Date(a.last_activity||0));
          const t=target('courier',recent[1]);
          return JSON.stringify({from:recent[1].name,to:recent[0].name,
            match:!!t&&t.at==='cell'&&t.id===recent[0].id,
            selfEdge:target('courier',recent[0])===null});})()"""))
        check("courier walks the real last_activity edge", edge["match"] is True,
              edge["from"] + " -> " + edge["to"])
        check("courier from the newest project is refused", edge["selfEdge"] is True,
              "no self-edge")
        # And that a courier actually dispatches when it is the only one eligible.
        got = None
        for _ in range(14):
            got = json.loads(js(ws, """(()=>{
              const act=PROJECTS.filter(p=>p._t!==3&&p.path_exists);
              const recent=act.slice().sort((a,b)=>
                new Date(b.last_activity||0)-new Date(a.last_activity||0));
              const src=recent[1];
              const save=act.map(p=>[p,p.waiting_count]);
              act.forEach(p=>{p.waiting_count=0});   // no messenger candidates
              // Snap everyone home first, or a cancelled trip leaves a villager
              // stranded mid-route and every later check inherits the mess.
              VILLS.forEach(v=>{v.trip=null;v.si=0;v.wx=v.hx;v.wy=v.hy;v.wz=v.hz;
                v.cool=v.id===src.id?0:1e12});
              dispatch();
              save.forEach(([p,w])=>{p.waiting_count=w});
              const v=VILLS.get(src.id);
              return JSON.stringify({kind:v.kind,trip:!!v.trip,mode:v.mode,cls:v.cls,
                steps:v.trip?v.trip.length:0});})()"""))
            if got["kind"] == "courier" and got["trip"]:
                break
        check("courier dispatches", got["kind"] == "courier" and got["trip"] is True, got)
        check("courier carries the violet cube", got["mode"] == "carry", got["mode"])
        # Three steps: journey, dwell, home. There used to be a fourth "out of
        # the yard" hop to a street at dep +0.15, which was deleted - it bought
        # nothing for occlusion (every hut is at dep -0.30, so the home line is
        # already in front of them), it dropped the sprite into the label chip,
        # and it walked at a third of the pace of the leg that followed it.
        check("courier trip is journey-dwell-home", got["steps"] == 3, got["steps"])
        # Reset. layout() re-homes anyone without a trip and rebuilds every node
        # in its Phase 1 slot, so it is the cheapest clean slate there is.
        js(ws, "VILLS.forEach(v=>{v.trip=null;v.si=0;v.cool=0});layout();"
               "dispatch();dispatch();dispatch()")
        time.sleep(0.4)

        print("")
        print("-- a journey survives layout(), the 30s poll, and a resize --")
        # Sampled, layout()ed and re-sampled inside ONE evaluate. Two separate
        # round-trips let a frame tick in between, and the villager legitimately
        # moves - which is what made an earlier run report "2 of 4 kept their
        # spot" against perfectly good code. The measurement has to be atomic.
        survive = json.loads(js(ws, """(()=>{
          const snap=()=>[...VILLS.values()].filter(v=>v.trip).map(v=>({
            id:v.id,si:v.si,wx:v.wx,wy:v.wy,wz:v.wz,tf:v.el.style.transform,
            trip:!!v.trip,inScene:v.el.parentNode===scene}));
          const pre=snap();
          layout();
          const post=snap();
          const p2=Object.fromEntries(post.map(r=>[r.id,r]));
          return JSON.stringify({n:pre.length,
            same:pre.filter(r=>p2[r.id]&&p2[r.id].wx===r.wx&&p2[r.id].wy===r.wy
              &&p2[r.id].wz===r.wz&&p2[r.id].trip&&p2[r.id].inScene).length,
            reprojected:pre.filter(r=>p2[r.id]&&p2[r.id].tf!==r.tf).length,
            bots:document.querySelectorAll('.bot').length,vills:VILLS.size,
            pre:pre.slice(0,2),post:post.slice(0,2)});})()"""))
        check("a journey was in flight to test", survive["n"] > 0, survive["n"])
        check("world position untouched by layout()",
              survive["same"] == survive["n"],
              str(survive["same"]) + " of " + str(survive["n"]) + " travellers kept "
              "their exact world spot, still travelling, still in the scene")
        check("villager count unchanged by layout()",
              survive["vills"] == survive["bots"],
              str(survive["vills"]) + " modelled / " + str(survive["bots"]) + " drawn")
        # A REAL resize, through CDP, not an inline width on #hive - that changes
        # nothing, because #hive is laid out by the page and an earlier version of
        # this check reported "SC moved" while SC had not moved at all. A genuine
        # viewport change re-solves SC/OX/OY, so the same world spot has to land
        # on new pixels. That is the difference between re-projecting a journey
        # and teleporting it home.
        js(ws, "window.__pre=JSON.stringify([...VILLS.values()].filter(v=>v.trip)"
               ".map(v=>({id:v.id,wx:v.wx,wy:v.wy,tf:v.el.style.transform})));window.__sc=SC")
        ws.call("Emulation.setDeviceMetricsOverride", width=1180, height=880,
                deviceScaleFactor=1, mobile=False)
        time.sleep(0.7)
        # A traveller keeps walking during the resize, so its world position is
        # SUPPOSED to advance and comparing it before and after proves nothing -
        # an earlier version of this check failed 3 of 3 on correct code for
        # exactly that reason. The invariant that does hold at every instant:
        # the drawn transform must equal iso() of the world position under the
        # CURRENT projection. If a resize teleported anyone, or left a stale
        # screen position behind, that equality breaks.
        rz = json.loads(js(ws, """(()=>{
          const pre=JSON.parse(window.__pre);
          const live=[...VILLS.values()].filter(v=>v.trip);
          // Compared as NUMBERS, not as strings: Chrome serialises a whole-number
          // pixel value as "100px" where toFixed(1) gives "100.0px", so a string
          // match fails at random depending on where a villager happens to be.
          const consistent=live.filter(v=>{
            const [sx,sy]=iso(v.wx,v.wy,v.wz);
            const m=(v.el.style.transform.match(/-?[\\d.]+/g)||[]).map(Number);
            return m.length===2&&Math.abs(m[0]-sx)<0.11&&Math.abs(m[1]-sy)<0.11;}).length;
          const post=Object.fromEntries(live.map(v=>[v.id,v]));
          return JSON.stringify({n:pre.length,live:live.length,
            consistent:consistent,
            survived:pre.filter(r=>post[r.id]).length,
            notHome:live.filter(v=>v.wx!==v.hx||v.wy!==v.hy).length,
            moved:pre.filter(r=>post[r.id]&&post[r.id].el.style.transform!==r.tf).length,
            scChanged:SC!==window.__sc,sc:SC,was:window.__sc});})()"""))
        ws.call("Emulation.clearDeviceMetricsOverride")
        time.sleep(0.5)
        check("resize really changed the projection", rz["scChanged"] is True,
              "SC " + str(round(rz["was"], 1)) + " -> " + str(round(rz["sc"], 1)))
        check("journeys survived the resize", rz["survived"] == rz["n"],
              str(rz["survived"]) + " of " + str(rz["n"]) + " still travelling")
        check("nobody teleported home mid-journey", rz["notHome"] == rz["live"],
              str(rz["notHome"]) + " of " + str(rz["live"]) + " still away from home")
        check("drawn position matches world position under the new SC",
              rz["consistent"] == rz["live"],
              str(rz["consistent"]) + " of " + str(rz["live"]) + " consistent")
        check("screen spot re-projected across resize", rz["moved"] == rz["n"],
              str(rz["moved"]) + " of " + str(rz["n"]) + " got a new transform")

        print("")
        print("-- nobody leaves a cell: the 'out of bounds from the nodes' bug --")
        # The owner's report, twice. A point-in-hexagon test of each traveller's FEET
        # against every cell's top face, sampled right through real trips. The
        # first time this was measured, messengers were the only offender - they
        # stood on bare ground 1.35 cells in front of the nearest row, which the
        # spec asked for - at 83 of 313 samples. Messengers stop at the front of
        # their OWN cell now, so this must come back empty.
        OOB = """(()=>{
          const inHex=(px,py,cx,cy,r)=>{const v=[];
            for(let i=0;i<6;i++){const t=Math.PI/6+i*Math.PI/3;
              v.push([cx+Math.cos(t)*r,cy+Math.sin(t)*r*0.58]);}
            let ins=false;
            for(let i=0,j=5;i<6;j=i++){const [xi,yi]=v[i],[xj,yj]=v[j];
              if((yi>py)!==(yj>py)&&px<(xj-xi)*(py-yi)/(yj-yi)+xi)ins=!ins;}
            return ins;};
          const cells=PROJECTS.concat(VACANT).filter(c=>c._x0!==undefined).map(c=>{
            const tz=c.vacant?VAC_T:(PLOT_T[c._t]||0.12);
            const t=iso(c._x0,c._y0,tz);
            return {cx:t[0],cy:t[1]};});
          const out=[];
          [...VILLS.values()].filter(v=>v.trip).forEach(v=>{
            const [sx,sy]=iso(v.wx,v.wy,v.wz);
            if(cells.some(c=>inHex(sx,sy,c.cx,c.cy,SC*0.995)))return;
            const p=PROJECTS.find(q=>q.id===v.id);
            const dep=p?+((v.wx+v.wy)-(p._x0+p._y0)).toFixed(3):null;
            out.push(v.kind+' step'+v.si+(v.trip[v.si].hold?' hold':'')
              +' at='+v.trip[v.si].at+' ownDepthOffset='+dep
              +' z='+(+v.wz.toFixed(3)));});
          return JSON.stringify(out);})()"""
        oob, oobn = {}, 0
        for i in range(70):
            if i % 10 == 0:
                js(ws, "VILLS.forEach(v=>{v.cool=0});for(let k=0;k<4;k++)dispatch()")
            time.sleep(0.22)
            for k in json.loads(js(ws, OOB)):
                oob[k] = oob.get(k, 0) + 1
                oobn += 1
            oobn += 0
        check("no traveller ever stood outside a cell", not oob,
              ("clean" if not oob else str(oobn) + " samples out of bounds: "
               + json.dumps(oob)))

        print("")
        print("-- targets survive a re-slot: the 'walks off the grid' bug --")
        # The owner watched villagers walk off the comb. Cause: the outbound targets
        # were world COORDINATES captured at dispatch, while place() re-slots
        # every cell from projects sorted by last_activity on each poll - which
        # is exactly the courier's trigger. The walker then kept heading for a
        # spot that now belonged to another project, or to empty comb.
        # Targets are descriptors resolved live now, so this asserts both the
        # structure and the behaviour.
        js(ws, "VILLS.forEach(v=>{v.cool=0});for(let i=0;i<8;i++)dispatch()")
        time.sleep(0.8)
        struct = json.loads(js(ws, """(()=>{
          const live=[...VILLS.values()].filter(v=>v.trip);
          const frozen=[];
          live.forEach(v=>v.trip.forEach((s,i)=>{
            if(!s.at||Array.isArray(s.to))frozen.push(v.id+' step'+i);}));
          return JSON.stringify({n:live.length,frozen:frozen});})()"""))
        check("no trip step carries a frozen coordinate",
              struct["n"] > 0 and not struct["frozen"],
              str(struct["n"]) + " trips, frozen steps: "
              + (str(struct["frozen"]) if struct["frozen"] else "none"))
        # Now force a genuine re-slot by inverting the activity order, and check
        # every live target still points at ITS OWN PROJECT's current cell.
        reslot = json.loads(js(ws, """(()=>{
          const live=[...VILLS.values()].filter(v=>v.trip&&v.trip[v.si].at==='cell');
          const before=live.map(v=>({id:v.id,dst:v.trip[v.si].id,
            to:resolve(v,v.trip[v.si]).slice(0,2)}));
          const save=PROJECTS.map(p=>[p,p.last_activity]);
          // Invert the ranking, which is what switching project really does.
          const n=PROJECTS.length;
          PROJECTS.forEach((p,i)=>{
            p.last_activity=new Date(Date.now()-(n-i)*3600000).toISOString();});
          layout();
          const moved=[],wrong=[];
          before.forEach(b=>{
            const v=VILLS.get(b.id); if(!v||!v.trip)return;
            const s=v.trip[v.si]; if(s.at!=='cell')return;
            const now=resolve(v,s);
            const p=PROJECTS.find(q=>q.id===s.id);
            // The live target must equal what the descriptor means RIGHT NOW.
            const want=besideW(p,s.lat||0);
            if(Math.abs(now[0]-want[0])>1e-9||Math.abs(now[1]-want[1])>1e-9)
              wrong.push(b.id);
            if(Math.abs(now[0]-b.to[0])>1e-6||Math.abs(now[1]-b.to[1])>1e-6)
              moved.push(b.id);
            // And the destination must still be a real, placed cell.
            if(!p||p._x0===undefined)wrong.push(b.id+' dangling');});
          save.forEach(([p,w])=>{p.last_activity=w}); layout();
          return JSON.stringify({tested:before.length,moved:moved.length,
            wrong:wrong});})()"""))
        check("a re-slot actually moved the targets", reslot["moved"] > 0,
              str(reslot["moved"]) + " of " + str(reslot["tested"]) + " re-resolved")
        check("every live target still points at its own project's cell",
              not reslot["wrong"],
              str(reslot["tested"]) + " tested, wrong: "
              + (str(reslot["wrong"]) if reslot["wrong"] else "none"))

        print("")
        print("-- sleepers never move --")
        now = by_id(json.loads(js(ws, STATE)))
        still = [k for k in sleepers
                 if now[k]["wx"] == home[k]["wx"] and now[k]["wy"] == home[k]["wy"]
                 and not now[k]["trip"] and now[k]["cls"] == "sleep"]
        check("every sleeper still home and asleep", len(still) == len(sleepers),
              str(len(still)) + " of " + str(len(sleepers)))
        # "Sleepers never move" also has to survive a TIER CHANGE. tier() reads
        # last_activity, so a project can cross the 30-day dormancy line while
        # its villager is out walking. Forced here by ageing a live traveller's
        # last_activity and re-running layout().
        flip = json.loads(js(ws, """(()=>{
          const v=[...VILLS.values()].find(x=>x.trip);
          if(!v)return JSON.stringify({none:true});
          const p=PROJECTS.find(x=>x.id===v.id), was=p.last_activity;
          const before={walking:!!v.trip,away:v.wx!==v.hx,cls:v.cls};
          p.last_activity=new Date(Date.now()-40*86400000).toISOString();
          layout();
          const w=VILLS.get(v.id);
          const after={trip:!!w.trip,sleep:!!w.sleep,cls:w.cls,
            atHome:w.wx===w.hx&&w.wy===w.hy&&w.wz===w.hz};
          p.last_activity=was; layout();      // put the scan back
          return JSON.stringify({id:v.id,before:before,after:after});})()"""))
        if flip.get("none"):
            check("a traveller was available for the dormancy flip", False, flip)
        else:
            check("was genuinely walking away from home before the flip",
                  flip["before"]["walking"] and flip["before"]["away"], flip["before"])
            check("falling dormant mid-journey stops the villager",
                  flip["after"]["trip"] is False and flip["after"]["sleep"] is True
                  and flip["after"]["atHome"] is True and flip["after"]["cls"] == "sleep",
                  flip["after"])

        print("")
        print("-- the launcher still works mid-walk --")
        print("  travellers now  : " + str(js(ws,
              "[...VILLS.values()].filter(v=>v.trip).length")))
        js(ws, "(()=>{const p=PROJECTS.find(x=>x.path_exists&&x._t!==3);"
               "document.querySelector('.plaque[data-id=\"'+p.id+'\"]')"
               ".dispatchEvent(new MouseEvent('click',{bubbles:true}));})()")
        time.sleep(0.9)
        check("bubble opened while villagers walk",
              js(ws, "!!document.getElementById('bubble')") is True,
              js(ws, "document.querySelector('#bubble h2')?.textContent"))
        js(ws, "closeBubble()")

        print("")
        print("-- everyone gets home and the loop idles out --")
        # Traffic has to be stopped first. The dispatcher is ambient and keeps
        # feeding the loop for as long as the page is open, so "RAF returns to 0"
        # is unobservable while it runs - not because the loop fails to idle.
        js(ws, "clearInterval(TRAFFIC)")
        for _ in range(80):
            time.sleep(0.5)
            if js(ws, "[...VILLS.values()].filter(v=>v.trip).length") == 0:
                break
        time.sleep(0.6)
        check("no trips left",
              js(ws, "[...VILLS.values()].filter(v=>v.trip).length") == 0)
        check("rAF idled itself out", js(ws, "RAF") == 0)
        check("everyone snapped exactly home", js(ws,
              "[...VILLS.values()].every(v=>v.wx===v.hx&&v.wy===v.hy&&v.wz===v.hz)") is True)
        check("trade resumed, nobody left walking",
              js(ws, "document.querySelectorAll('.bot.walk,.bot.wait').length") == 0)
        # The Phase 1 invariant, restored: a villager at rest sits immediately
        # after its own cell in the child list.
        check("back in the Phase 1 slot", js(ws,
              "[...VILLS.values()].every(v=>v.cellG.nextSibling===v.el)") is True)

        print("")
        print("PHASE 2: " + ("all checks passed" if not FAILS
                             else str(len(FAILS)) + " FAILED -> " + " | ".join(FAILS)))
        return 1 if FAILS else 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
