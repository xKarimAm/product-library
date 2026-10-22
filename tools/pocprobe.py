"""Measure the POC city: skyline, power grid, right rail, day/night, traffic and
the RCI meter. Numbers, not eyeballing. Exits 1 on any failed check.

  py tools/pocprobe.py

Two rules this probe keeps, both paid for by an independent mutation review on
2026-10-14 (11 of 18 planted defects survived the first version):

1. EXPECTATIONS ARE DERIVED INDEPENDENTLY. A check that builds its expected set
   with the page's own helper (isLot, tier, applySky) agrees with any bug in that
   helper. Expected lots come from poc_data.json in Python; expected meter bars
   from raw last_activity; the clock is advanced through layout(), the path the
   30s poll takes, never by calling applySky() directly.
2. CONTROLS. Where a check could pass for the wrong reason, the probe plants the
   defect on purpose and requires the same check to fail.
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "file:///" + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "poc_city.html").replace("\\", "/")
FAILS = []


def check(ok, label, detail=""):
    print(("  PASS " if ok else "  FAIL ") + label + ("   " + str(detail) if detail != "" else ""))
    if not ok:
        FAILS.append(label)


def control(caught, label):
    """A control passes when the check it guards CAUGHT the planted defect."""
    check(caught, "control: " + label + " is caught")


def J(ws, expr):
    """Evaluate in the page; a page exception stops the run instead of reading as a value."""
    r = js(ws, expr)
    if isinstance(r, str) and r.startswith("ERROR"):
        raise SystemExit("page error in probe expression: " + r + "\n" + expr[:300])
    return json.loads(r) if isinstance(r, str) and r[:1] in "[{" else r


def size(ws, w, h):
    """Set the VIEWPORT, not the window: --window-size=1600,1000 measured 1582x904."""
    ws.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
    time.sleep(0.9)                       # the resize listener debounces layout() by 130ms
    J(ws, "layout()")
    return J(ws, "JSON.stringify([innerWidth,innerHeight])")


def ready(ws, extra=""):
    # 90s cap, left early the moment the page is ready. 30s was too short with
    # several Chromes running at once (the mutation re-test) and read as a failure.
    for _ in range(180):
        time.sleep(0.5)
        if js(ws, "typeof TRAFFIC!=='undefined' && VILLS.size>0 && "
                  "document.querySelectorAll('#scene .bot').length>0 && !!document.getElementById('rci')" + extra):
            return
    raise SystemExit("page never became ready")


# The same fallback build_poc.py uses: a real scan if present, else the sample.
_real = os.path.join(HERE, "poc_data.json")
DATA = json.load(open(_real if os.path.exists(_real) else os.path.join(HERE, "sample_data.json"),
                      encoding="utf-8"))
WANT_LOTS = sorted(p["id"] for p in DATA if not (p.get("waiting_count") or p.get("blocker_count")
                   or p.get("has_state") or p.get("branch") or p.get("sessions")))

# ?hour=3 so the FIRST render must come up as night with no help from the probe:
# that is the only thing in this run that exercises the ?hour= parameter.
proc, ws = attach(URL + "?hour=3", "1600,1000")
try:
    # Wait for TRAFFIC itself, not a fixed delay. load() arms the dispatcher 3s
    # AFTER the first render, so clearing it any earlier clears a 0 handle and
    # the interval starts anyway - every vehicle check then races live spawning.
    ready(ws, " && TRAFFIC!==0")
    check(J(ws, "hive.dataset.tod") == "night", "?hour=3 renders night on first paint", J(ws, "hive.dataset.tod"))
    # Trap 18: both intervals stop, so nothing spawns or re-lays out under us.
    J(ws, "clearInterval(TRAFFIC);clearInterval(POLL);VEHS.forEach(dropVeh);VILLS.forEach(v=>{v.trip=null});layout();")
    time.sleep(3.6)                       # more than two dispatch periods
    st = J(ws, "JSON.stringify({veh:VEHS.size,trips:[...VILLS.values()].filter(v=>v.trip).length})")
    check(st["veh"] == 0 and st["trips"] == 0, "the dispatcher is really stopped", st)
    print("  viewport       :", size(ws, 1600, 1000))
    J(ws, "window.POC_HOUR=12;layout();")

    # ------------------------------------------------------------ skyline
    print("skyline")
    print("  hut groups     :", J(ws, "document.querySelectorAll('#scene .hut').length"))
    print("  windows        :", J(ws, "document.querySelectorAll('#scene .win').length"))
    print("  cranes         :", J(ws, "document.querySelectorAll('#scene .crane').length"))
    tow = J(ws, """JSON.stringify([...document.querySelectorAll('#scene .hut')].map(h=>{
        const r=h.getBoundingClientRect();return {h:Math.round(r.height)};}))""")
    print("  heights px     :", sorted(t["h"] for t in tow))
    NAN = """[...document.querySelectorAll('#scene *')].filter(n=>['points','d','transform','cx','cy','x','y']
        .some(a=>/NaN|Infinity/.test(n.getAttribute(a)||''))).length"""
    nan = J(ws, NAN)
    flat = len([t for t in tow if t["h"] < 10])
    check(nan == 0 and flat == 0, "every tower has real geometry",
          "NaN/Infinity attributes=%s, towers under 10px=%d" % (nan, flat))

    # ---------------------------------------------------------- power grid
    print("power grid")
    g = J(ws, """JSON.stringify((()=>{
      const plq=[...document.querySelectorAll('#scene .plaque[data-id]')];
      const withLot=plq.filter(c=>c.querySelector('.lot')).map(c=>c.dataset.id).sort();
      return {proj:PROJECTS.length, lotIds:withLot,
        lots:document.querySelectorAll('#scene .lot').length,
        huts:document.querySelectorAll('#scene .hut').length,
        hutOnLot: plq.filter(c=>c.querySelector('.lot')&&c.querySelector('.hut')).length,
        dead: plq.filter(c=>c.querySelector('.lot .deadlamp')).length,
        glowOnLot: plq.filter(c=>c.querySelector('.lot')&&c.querySelector('.lampglow')).length};})())""")
    print("   %d lots, %d towers, %d projects" % (g["lots"], g["huts"], g["proj"]))
    check(g["lotIds"] == WANT_LOTS and len(WANT_LOTS) > 0,
          "lots are exactly the grey stubs in poc_data.json", "%d drawn, %d expected" % (len(g["lotIds"]), len(WANT_LOTS)))
    check(g["lots"] + g["huts"] == g["proj"], "every project is a tower or a lot, never both or neither",
          "%d + %d vs %d" % (g["lots"], g["huts"], g["proj"]))
    check(g["hutOnLot"] == 0 and g["glowOnLot"] == 0 and g["dead"] == g["lots"],
          "a lot has no tower, no lit lamp, one dead lamp")

    # ----------------------------------------------------------- right rail
    print("right rail")
    r = J(ws, """JSON.stringify((()=>{
      const a=document.getElementById('app').getBoundingClientRect(),
            h=hive.getBoundingClientRect(), r=document.getElementById('roster').getBoundingClientRect();
      const L=document.querySelector('#roster .rlist'); L.scrollTop=1e6;
      const last=[...L.querySelectorAll('button.r')].pop().getBoundingClientRect(), lr=L.getBoundingClientRect();
      return {appR:a.right, railR:r.right, railL:r.left, hiveR:h.right, railTop:r.top, hiveTop:h.top,
              railBot:r.bottom, vh:innerHeight, lastBot:last.bottom, listBot:lr.bottom,
              rows:L.querySelectorAll('button.r').length, proj:PROJECTS.length,
              legend:!!document.querySelector('#roster .rfoot'),
              hiveLegend:getComputedStyle(document.querySelector('#hive>.legend')).display};})())""")
    print("  ", r)
    check(abs(r["railR"] - r["appR"]) < 1 and r["hiveR"] <= r["railL"] + 0.5,
          "rail is docked right and the hive ends where it begins")
    check(abs(r["railTop"] - r["hiveTop"]) < 1 and abs(r["railBot"] - r["vh"]) < 1,
          "rail is full height under the header")
    check(r["rows"] == r["proj"] and r["lastBot"] <= r["listBot"] + 0.5,
          "every project has a row and the last row is not clipped")
    check(r["legend"] and r["hiveLegend"] == "none", "legend lives in the rail, once")
    # The 30s poll rebuilds the list; a keyboard user must keep their place.
    # Scroll to whatever the list can actually scroll (a short list cannot reach
    # 120px) and require the poll to keep exactly that.
    kept = J(ws, """JSON.stringify((()=>{const L=document.querySelector('#roster .rlist');
      L.scrollTop=Math.min(120,L.scrollHeight-L.clientHeight);const want=L.scrollTop;
      const bs=L.querySelectorAll('button.r'), b=bs[Math.min(9,bs.length-1)];b.focus();const id=b.dataset.id;
      buildRoster();const L2=document.querySelector('#roster .rlist');
      return {top:L2.scrollTop, want, same:document.activeElement.dataset&&document.activeElement.dataset.id===id};})())""")
    check(kept["top"] == kept["want"] and kept["same"], "a poll keeps the rail's scroll and focus", kept)

    # ------------------------------------------------- labels and the meter
    print("labels and meter")
    CLASH = """(()=>{const ns=[...document.querySelectorAll('#nodes .node')];let n=0;
      ns.forEach(a=>{const m=a.querySelector('.meta');if(!m)return;const r=m.getBoundingClientRect();
        ns.forEach(b=>{if(a===b)return;const q=b.getBoundingClientRect();
          if(r.right>q.left&&r.left<q.right&&r.bottom>q.top&&r.top<q.bottom)n++;});});return n;})()"""
    check(J(ws, CLASH) == 0, "no meta line overlaps another label",
          "meta shown=%s" % J(ws, "document.querySelectorAll('#nodes .meta').length"))
    m = J(ws, """JSON.stringify((()=>{
      const bars=[...document.querySelectorAll('#rci .bar s')].map(s=>+s.textContent);
      const age=p=>p.last_activity?Date.now()-Date.parse(p.last_activity):Infinity;
      const W=PROJECTS.filter(p=>(p.waiting_count||0)>0).length;
      const A=PROJECTS.filter(p=>!(p.waiting_count>0)&&age(p)<=30*86400000).length;
      return {bars, want:[W,A,PROJECTS.length-W-A],
        pop:+document.querySelector('#rci .pop b').textContent};})())""")
    sess = sum(p.get("sessions") or 0 for p in DATA)
    print("  ", m)
    check(m["bars"] == m["want"], "W/A/D bars match an independent count of the data")
    check(m["pop"] == sess, "POP is total sessions in poc_data.json", "%s vs %s" % (m["pop"], sess))
    METER = """(()=>{const m=document.getElementById('rci').getBoundingClientRect();
      const hit=[...document.querySelectorAll('#nodes .node,#scene .plaque[data-id] .cell-t,#scene .hut,#scene .lot')].filter(n=>{
        const q=n.getBoundingClientRect();return m.right>q.left&&m.left<q.right&&m.bottom>q.top&&m.top<q.bottom;});
      return JSON.stringify({hit:hit.length,SC:+SC.toFixed(1)});})()"""
    for w, h in [(1600, 1000), (1920, 1080), (1440, 900), (1366, 768), (1280, 800), (1024, 768)]:
        size(ws, w, h)
        o = J(ws, METER)
        check(o["hit"] == 0, "meter covers no label or cell at %dx%d" % (w, h), o)
    # Control: lay out with the meter's reservation defeated (meter invisible to
    # fit), then put it back. At 1440x900 the corner cell must land under it.
    # style.display, NOT the hidden attribute: #rci{display:flex} outranks the
    # UA's [hidden] rule, so `hidden` left the meter measurable and this control
    # silently tested nothing on its first run.
    # Whether an unreserved layout puts a cell under the meter depends on the
    # data (the real 2026-10-14 scan does at 1440x900; the sample projects do not
    # at any size tried). So: plant the real defect where it shows, and where it
    # does not, plant the meter directly over a cell. Either way the check must
    # see the overlap.
    bad = None
    for w, h in [(1440, 900), (1600, 1000), (1920, 1080)]:
        size(ws, w, h)
        o = J(ws, "(()=>{const m=document.getElementById('rci');m.style.display='none';layout();m.style.display='';"
                  "const r=%s;layout();return r;})()" % METER)
        if o["hit"] > 0:
            bad = dict(o, how="fit() without the reservation at %dx%d" % (w, h))
            break
    if bad is None:
        bad = J(ws, "(()=>{const m=document.getElementById('rci'),c=document.querySelector('#scene .plaque[data-id] .cell-t')"
                    ".getBoundingClientRect(),hv=hive.getBoundingClientRect();"
                    "m.style.left=(c.left-hv.left)+'px';m.style.bottom=(hv.bottom-c.bottom)+'px';"
                    "const r=%s;m.style.left='';m.style.bottom='';return r;})()" % METER)
        bad["how"] = "meter moved over a cell"
    print("   control planted:", bad["how"])
    control(bad["hit"] > 0, "a meter over a cell")
    size(ws, 1600, 1000)

    # ------------------------------------------------------------ day/night
    print("day/night")
    # Through layout(), the path the poll takes - not applySky() directly.
    SKY = """(h=>{window.POC_HOUR=h;layout();
      // Flickering windows (city: shine) change fill on a timer, so the palette
      // rules are checked on the still ones; the flicker has its own check.
      const still=x=>getComputedStyle(x).animationName==='none', all=[...document.querySelectorAll('#scene .win')];
      const w=all.filter(still), f=x=>getComputedStyle(x).fill;
      const on=[...document.querySelectorAll('#scene .win.on:not(.dim)')].filter(still), off=[...document.querySelectorAll('#scene .win:not(.on)')].filter(still);
      return JSON.stringify({tod:hive.dataset.tod,
        g0:getComputedStyle(hive).getPropertyValue('--ground-0').trim(),
        ground:getComputedStyle(document.querySelector('.lyr.ground')).backgroundImage.slice(0,60),
        lit:w.filter(x=>f(x)==='rgb(255, 216, 114)').length, all:w.length,
        onOk:on.length>0&&on.every(x=>f(x)==='rgb(244, 192, 78)'),
        offOk:off.length>0&&off.every(x=>x.closest('.hut.cold')?f(x)==='rgb(34, 29, 46)':f(x)==='rgb(42, 36, 56)'),
        flick:all.length-w.length, total:all.length,
        clock:document.querySelector('#rci .clock').textContent});})"""
    seen = {}
    for h, want in [(3, "night"), (7, "dawn"), (12, "day"), (19.25, "dusk"), (23, "night")]:
        s = J(ws, SKY + "(%s)" % h)
        print("   %5s  tod=%s g0=%s lit=%d/%d clock=%r" % (h, s["tod"], s["g0"], s["lit"], s["all"], s["clock"]))
        seen[h] = s
        check(s["tod"] == want and s["clock"].endswith(want), "hour %s reads as %s, clock agrees" % (h, want))
        if want == "night":
            check(s["lit"] == s["all"] and s["all"] > 0, "night at %s lights every window" % h,
                  "%d/%d" % (s["lit"], s["all"]))
        else:
            check(s["lit"] == 0 and s["onOk"] and s["offOk"],
                  "%s draws windows by recency: lit amber, unlit dark" % want)
    fl = seen[12]
    check(0 < fl["flick"] < fl["total"] * 0.2, "a few windows flicker, the skyline stays lit",
          "%d/%d" % (fl["flick"], fl["total"]))
    check(len({seen[h]["ground"] for h in (3, 7, 12, 19.25)}) == 4,
          "the ground actually renders differently in all four phases")
    check(seen[12]["g0"] == "#1b0a3d", "midday is the original palette", seen[12]["g0"])
    nanh = J(ws, "(()=>{window.POC_HOUR=NaN;layout();const g=getComputedStyle(hive).getPropertyValue('--ground-0');"
                 "window.POC_HOUR=12;layout();return g;})()")
    check(isinstance(nanh, str) and "NaN" not in nanh, "a non-finite POC_HOUR falls back to the clock", nanh)
    # Control: take the real night window rule out of the stylesheet and put it
    # back. Without it, night must FAIL to light every window.
    planted = J(ws, """(()=>{const out=[];
      [...document.styleSheets].forEach(sh=>{const rs=sh.cssRules;
        for(let i=rs.length-1;i>=0;i--){const t=rs[i].selectorText||'';
          if(t.includes('data-tod="night"')&&t.includes('.win')){out.push([sh,i,rs[i].cssText]);sh.deleteRule(i);}}});
      const r=""" + SKY + """(3);
      out.reverse().forEach(([sh,i,css])=>sh.insertRule(css,i));
      const back=""" + SKY + """(3);
      return JSON.stringify({removed:out.length, without:JSON.parse(r), back:JSON.parse(back)});})()""")
    control(planted["removed"] == 1 and planted["without"]["lit"] < planted["without"]["all"]
            and planted["back"]["lit"] == planted["back"]["all"], "night with its window rule removed")
    J(ws, "window.POC_HOUR=12;layout();")

    # -------------------------------------------------------------- traffic
    print("traffic")
    roads = J(ws, "JSON.stringify({n:document.querySelectorAll('#scene .roads .road').length,gap:AVE.gap,front:AVE.front})")
    check(roads["n"] == (2 if roads["gap"] is not None else 1) and roads["front"] is not None,
          "an avenue is drawn for each district boundary", roads)
    ORDER = """(id=>{const v=VEHS.get(id);if(!v)return JSON.stringify({gone:true});
      const kids=[...scene.children], at=kids.indexOf(v.el);
      const cells=kids.map((n,i)=>({n,i})).filter(o=>o.n.classList&&o.n.classList.contains('plaque')&&o.n.dataset.id);
      const band=(n)=>{const p=PROJECTS.find(q=>q.id===n.dataset.id);return p?p._b:-1;};
      const tops=b=>[...document.querySelectorAll('#scene .plaque[data-id]')].filter(n=>band(n)===b)
        .map(n=>n.querySelector('.cell-t').getBoundingClientRect());
      const box=v.el.getBoundingClientRect(), hv=hive.getBoundingClientRect();
      return JSON.stringify({kind:v.kind, ave:v.ave, at, connected:v.el.isConnected,
        y:box.bottom, x:box.left+box.width/2, w:box.width, hiveBot:hv.bottom,
        liveAfter:cells.filter(o=>o.i>at&&band(o.n)===0).length,
        liveBefore:cells.filter(o=>o.i<at&&band(o.n)===0).length,
        dormAfter:cells.filter(o=>o.i>at&&band(o.n)===1).length,
        liveCellBottom:Math.max(...tops(0).map(r=>r.bottom)),
        liveCellTop:Math.min(...tops(0).map(r=>r.top)),
        dormCellBottom:tops(1).length?Math.max(...tops(1).map(r=>r.bottom)):null});})"""
    ids = J(ws, """JSON.stringify((()=>{const L=PROJECTS.filter(p=>p._b===0&&!isLot(p));
      const S=PROJECTS.filter(p=>p._t===1&&p.has_state);
      const c=spawnVehicle('car',L[0].id,L[L.length-1].id);
      const t=spawnVehicle('truck','L',(S[0]||L[1]).id);
      return {car:c&&c.id, truck:t&&t.id, gap:AVE.gap, carTo:L[L.length-1].id};})())""")
    check(bool(ids["car"]) and bool(ids["truck"]), "a car and a truck can be put on the road")
    time.sleep(0.6)

    def placement(tag):
        c = J(ws, ORDER + "(%s)" % json.dumps(ids["car"]))
        t = J(ws, ORDER + "(%s)" % json.dumps(ids["truck"]))
        print("   %s car   %s" % (tag, {k: c.get(k) for k in ("ave", "connected", "liveAfter", "y", "w")}))
        print("   %s truck %s" % (tag, {k: t.get(k) for k in ("ave", "connected", "liveBefore", "dormAfter", "y")}))
        check(c.get("connected") and c["ave"] == "front" and c["liveAfter"] == 0
              and c["liveCellBottom"] < c["y"] <= c["hiveBot"] and c["w"] > 4,
              "%s: the car is drawn in front of the live comb, inside the hive" % tag)
        if ids["gap"] is not None:
            check(t.get("connected") and t["ave"] == "gap" and t["liveBefore"] == 0 and t["dormAfter"] == 0
                  and t["liveAfter"] > 0, "%s: the truck paints after every dormant cell and before every live one" % tag)
            check(t["dormCellBottom"] < t["y"] < t["liveCellTop"] + 12, "%s: the truck sits between the combs" % tag)
        return c

    c0 = placement("on spawn")
    check(J(ws, NAN) == 0, "no vehicle is drawn at NaN")
    # The 30s poll re-runs layout(), which detaches every <g> - vehicles too.
    J(ws, "layout()")
    c1 = placement("after layout()")
    # Re-slot under a moving car: promote its destination to most recent, which
    # moves it to another comb slot. The car must be CARRIED, not snapped.
    rs = J(ws, """(id=>{const v=VEHS.get(%s);J0=v.el.getBoundingClientRect();
      const p=PROJECTS.find(q=>q.id===id), x0=p._x0;p.last_activity=new Date().toISOString();layout();
      const J1=v.el.getBoundingClientRect();
      return JSON.stringify({moved:p._x0!==x0, dx:Math.round((J1.left+J1.width/2)-(J0.left+J0.width/2))});})(%s)"""
           .replace("J0=", "const J0=") % (json.dumps(ids["car"]), json.dumps(ids["carTo"])))
    print("   re-slot", rs)
    check(rs["moved"] and abs(rs["dx"]) <= 6, "a re-slot carries a moving car instead of snapping it", rs)
    if ids["gap"] is not None:
        # Control: append the truck at the very end, where a vehicle with no
        # depth bucket would land. The same order test must now fail.
        bad = J(ws, "(()=>{scene.appendChild(VEHS.get(%s).el);return %s(%s);})()"
                % (json.dumps(ids["truck"]), ORDER, json.dumps(ids["truck"])))
        control(bad["liveAfter"] == 0 and bad["liveBefore"] > 0, "a truck with no depth bucket")
        J(ws, "(()=>{const v=VEHS.get(%s);if(v){v.bucket=-1;placeVeh(v,vehPos(v,performance.now()));}})()"
          % json.dumps(ids["truck"]))
    # TRAFFIC is cleared, so nothing new spawns: every vehicle must finish its
    # trip and the one rAF loop must die. That is trap 18's invariant, kept.
    t0 = time.time()
    while time.time() - t0 < 45:
        st = J(ws, "JSON.stringify({n:VEHS.size,raf:RAF,dom:document.querySelectorAll('#scene .veh').length})")
        if st["n"] == 0 and st["raf"] == 0:
            break
        time.sleep(0.5)
    check(st["n"] == 0 and st["dom"] == 0 and st["raf"] == 0,
          "every vehicle finishes and the rAF loop dies", "%s after %.1fs" % (st, time.time() - t0))
    # Traffic as a SIGNAL: the dispatcher itself must put cars on the road when
    # the data says projects were switched today. Two live projects are made
    # "touched this hour" so the check does not depend on when the scan was taken.
    sig = J(ws, """JSON.stringify((()=>{const L=PROJECTS.filter(p=>p._b===0&&!isLot(p));
      L[0].last_activity=new Date(Date.now()-3600e3).toISOString();
      L[1].last_activity=new Date(Date.now()-7200e3).toISOString();layout();
      let n=0;for(let i=0;i<40&&!n;i++){dispatch();VEHS.forEach(v=>{if(v.kind==='car')n++;});}
      const out={cars:n,recent:trafficNow().recent.length};VEHS.forEach(dropVeh);
      VILLS.forEach(v=>{v.trip=null});layout();return out;})())""")
    check(sig["cars"] > 0 and sig["recent"] >= 2, "dispatch() sends cars when projects were switched today", sig)

    # ------------------------------------------------------- rail collapse
    print("rail collapse")
    RAILW = "JSON.stringify({hw:hive.clientWidth,vb:+scene.getAttribute('viewBox').split(' ')[2],SC:+SC.toFixed(2)})"
    a = J(ws, RAILW)
    J(ws, "document.querySelector('#roster .rhead').click()")
    time.sleep(0.9)
    b = J(ws, RAILW)
    print("   open  ", a)
    print("   shut  ", b)
    check(b["hw"] > a["hw"] + 150 and b["vb"] == b["hw"], "collapsing the rail re-lays the city into the space")
    J(ws, "document.querySelector('#roster .rhead').click()")
    time.sleep(0.9)
    c2 = J(ws, RAILW)
    check(c2 == a, "re-opening the rail puts the city back exactly", c2)
    # Control: shut the rail WITHOUT the layout call. The hive widens but the
    # scene keeps the old viewBox - the same check must fail.
    J(ws, "document.getElementById('roster').classList.add('shut')")
    time.sleep(0.9)
    d = J(ws, RAILW)
    control(not (d["hw"] > a["hw"] + 150 and d["vb"] == d["hw"]), "a collapse that never re-runs layout()")
    J(ws, "document.getElementById('roster').classList.remove('shut');")
    time.sleep(0.9)
    J(ws, "layout()")

    # ------------------------------------------------------ reduced motion
    print("reduced motion, switched on mid-flight")
    J(ws, "(()=>{const L=PROJECTS.filter(p=>p._b===0);spawnVehicle('car',L[0].id,L[L.length-1].id);})()")
    pre = J(ws, "VEHS.size")
    ws.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    time.sleep(0.6)
    rm = J(ws, """JSON.stringify((()=>{const s=spawnVehicle('car',PROJECTS[0].id,PROJECTS[1].id);
      for(let i=0;i<8;i++)dispatch();
      return {rm:RM.matches,n:VEHS.size,spawned:!!s,dom:document.querySelectorAll('#scene .veh').length};})())""")
    time.sleep(0.4)
    rm["raf"] = J(ws, "RAF")
    print("   before %s, after %s" % (pre, rm))
    check(pre >= 1 and rm["rm"] and rm["n"] == 0 and rm["dom"] == 0 and not rm["spawned"] and rm["raf"] == 0,
          "reduced motion parks every vehicle and spawns none")
finally:
    proc.terminate()

# A fresh page with reduced motion on from the very first paint: count every
# requestAnimationFrame the page makes, from before its own scripts run.
print("reduced motion, from first paint")
# Start on about:blank and NAVIGATE after injecting, rather than reloading: an
# evaluate sent while a reload is tearing the old context down can go unanswered
# until the socket times out, which is what happened with four probes in parallel.
proc, ws = attach("about:blank", "1600,1000", extra=["--force-prefers-reduced-motion"])
try:
    ws.call("Page.addScriptToEvaluateOnNewDocument", source=(
        "window.__raf=0;const __r=window.requestAnimationFrame.bind(window);"
        "window.requestAnimationFrame=function(f){window.__raf++;return __r(f);};"))
    ws.call("Page.navigate", url=URL)
    time.sleep(2.0)
    ready(ws)
    time.sleep(1.5)
    o = J(ws, "JSON.stringify({rm:RM.matches,raf:window.__raf,RAF,veh:VEHS.size,"
              "caret:getComputedStyle(document.querySelector('#roster .caret')).transitionDuration})")
    print("  ", o)
    check(o["rm"] and o["raf"] == 0 and o["RAF"] == 0 and o["veh"] == 0 and o["caret"] == "0s",
          "reduced motion schedules no rAF and transitions nothing", o)
finally:
    proc.terminate()

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), "; ".join(FAILS)))
    sys.exit(1)
print("all checks passed")
