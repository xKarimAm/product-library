"""Phase 3 acceptance: cursor proximity - the greeting wave, the sleeper's opened
lid, and the assertion that the eyes NEVER move. Harness only; ships with nothing.

Eye tracking was built, shown to the owner, and cut. Most of this file is therefore a
guard against it coming back, and it carries a POSITIVE CONTROL that displaces one
eyes group for real on every run: "the detector stayed silent" is worth nothing
until the detector is shown to be capable of speaking.

Everything here is MEASURED off a live page through CDP. Nothing is asserted by
reading index.html, because three of this project's own checks were wrong before
the code was (see tools/phase2.py).

The cursor is moved with a real Input.dispatchMouseEvent rather than by calling
onMove() directly, so the listener, the rAF coalescing and the viewport->scene
conversion are all inside the measured path. Calling the handler would prove the
maths and skip the wiring.

  py phase3.py              normal
  py phase3.py --reduced    prefers-reduced-motion: none of it may run
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import attach, js

URL = "http://127.0.0.1:7777/"
FAILS = []


def check(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + ("  " + str(detail) if detail != "" else ""))
    if not ok:
        FAILS.append(name)


def move(ws, x, y):
    """A real mouse move, then a beat for the rAF frame to land."""
    ws.call("Input.dispatchMouseEvent", type="mouseMoved", x=float(x), y=float(y),
            button="none", clickCount=0)
    time.sleep(0.14)


def park(ws):
    """Freeze the world, so a villager's position is a constant for the rest of
    the run.

    TWO intervals have to stop, not one. Clearing only TRAFFIC leaves the 30s
    `load` poll running, and this suite comfortably outlasts 30s - the sweep alone
    is 25 villagers x 12 probes x 0.14s. A poll landing mid-run calls layout(),
    which re-runs place()/fit(), replaces every v.el and resets greet/peek, while
    anchors() was captured once at the top. Every cursor target after that points
    at where a villager used to be, and the failures look random."""
    js(ws, "clearInterval(TRAFFIC);if(typeof POLL!=='undefined')clearInterval(POLL);"
           "VILLS.forEach(v=>{v.trip=null;v.si=0;v.cool=1e12});layout()")
    time.sleep(0.5)
    return js(ws, "typeof POLL!=='undefined'")


def anchors(ws):
    """Every villager's EYE position in viewport coordinates, plus SC.

    The eyes, not the feet: v.sx/v.sy anchor the feet, and aiming the cursor
    there would test a point 7.5 sprite pixels below the thing being tracked."""
    # typeof v.sx is tested, not assumed. Run against a build without the stored
    # screen position and the arithmetic below yields null, which used to reach
    # Python as None and crash the suite with a TypeError several checks later -
    # a traceback instead of the finding. A missing prerequisite is a FAIL with a
    # name, like everything else here.
    return js(ws,
        "(()=>{const r=scene.getBoundingClientRect();const out=[];let noPos=0;"
        "VILLS.forEach(v=>{if(!v.el||!v.el.isConnected)return;"
        "if(typeof v.sx!=='number'||typeof v.sy!=='number'){noPos++;return;}"
        "out.push({id:v.id,sleep:!!v.sleep,"
        "ax:r.left+v.sx,ay:r.top+v.sy-(SPR_H-1.5)*(v.px||3),px:(v.px||3)});});"
        "return {SC:SC,vills:out,noPos:noPos,total:VILLS.size};})()")


def state(ws, vid):
    """One villager's Phase 3 state, read off the DOM and the model together."""
    return js(ws,
        "(()=>{const v=VILLS.get(" + repr(vid).replace("'", '"') + ");"
        "if(!v||!v.el)return null;const cs=getComputedStyle(v.el.querySelector('.wav'));"
        "const lid=getComputedStyle(v.el.querySelector('.lid'));"
        "const eg=v.el.querySelector('.eyes');const es=getComputedStyle(eg);"
        "return {ex:v.el.style.getPropertyValue('--ex'),"
        "ey:v.el.style.getPropertyValue('--ey'),"
        "cls:v.el.getAttribute('class'),"
        "greet:v.el.classList.contains('greet'),"
        "peek:v.el.classList.contains('peek'),"
        "wav:cs.opacity,lid:lid.opacity,"
        "eyeTr:es.transform,eyeTl:es.translate,"
        "mgreet:!!v.greet,mpeek:!!v.peek};})()")


def all_offsets(ws):
    return js(ws, "[...document.querySelectorAll('#scene .bot')].map("
                  "b=>b.style.getPropertyValue('--ex')+'|'+b.style.getPropertyValue('--ey'))")


def eyes_moved(ws):
    """Every way an eyes group could be displaced, asked of COMPUTED style.

    The owner rejected eye tracking on sight - "no need for the eyes to get detached
    from the body" - and the mechanism is not the obvious one. rects() emits a
    rect only for '#' cells, and BOT row 1 is "..#o##o#..", so .body paints
    NOTHING at x=3 or x=6: the eye sockets are holes and the pupils inside .eyes
    are the only paint covering them. Displace .eyes and two background-coloured
    holes open in the face, on EVERY non-zero offset. So this is not a range check
    on an offset, it is the assertion that no offset exists at all.
    MEASURED GEOMETRICALLY, against the parent. An earlier version of this read
    getComputedStyle().transform/.translate and compared them to 'none', and it
    was worthless: it reports 'none' for an SVG `transform` ATTRIBUTE, and it
    reports 'none' for a rule the page never received. A harness that cannot tell
    "nothing moved" from "I measured nothing" is not a harness. .eyes sits
    directly inside .body with no transform of its own, so an undisplaced group
    has exactly its parent's CTM and ANY displacement - CSS property, presentation
    attribute, or animation - shows up as a delta, whatever put it there."""
    return js(ws,
        "[...document.querySelectorAll('#scene .bot .eyes')].map(g=>{"
        "const m=g.getCTM(),p=g.parentNode.getCTM();"
        "if(!m||!p)return null;const dx=m.e-p.e,dy=m.f-p.f;"
        "return (Math.abs(dx)>0.01||Math.abs(dy)>0.01)?(dx.toFixed(2)+','+dy.toFixed(2)):null;"
        "}).filter(Boolean)")


def sleepers_greeting(ws):
    """The spec's hard scope: the wave is never on a sleeper. Asked of the DOM,
    so it covers a class written by any path, not just the one under test."""
    return js(ws, "document.querySelectorAll('#scene .bot.sleep.greet').length")


def main():
    reduced = "--reduced" in sys.argv
    extra = ["--force-prefers-reduced-motion"] if reduced else None
    proc, ws = attach(URL, "1600,1000", extra)
    try:
        # Wait for the MODEL, not just for sprites. A cold scan of the 60MB corpus
        # can take seconds (trap 15), and a page caught between the two renders
        # has .bot nodes whose VILLS entries have not been through villager() yet,
        # so v.sx is missing and every cursor target below is wrong. Requiring
        # VILLS.size as well closes that window; it cost one unreproducible
        # "ERROR: Uncaught" to find.
        for _ in range(60):
            time.sleep(0.5)
            if js(ws, "typeof VILLS!=='undefined' && VILLS.size>0 && "
                      "document.querySelectorAll('#scene .bot').length>0"):
                break
        time.sleep(1.0)
        pollable = park(ws)

        info = anchors(ws)
        # js() reports a page-side exception by RETURNING the string "ERROR: ...",
        # it does not raise. Indexing that string straight away turns a readable
        # page error into "TypeError: string indices must be integers" several
        # lines from the cause, which is exactly what it did once here.
        if isinstance(info, str):
            raise SystemExit("scene probe failed in the page: " + info)
        if not info:
            raise SystemExit("could not read the scene - is `py coc.py` running?")
        SC = info["SC"]
        vills = info.get("vills") or []
        awake = [v for v in vills if not v["sleep"]]
        asleep = [v for v in vills if v["sleep"]]
        print("mode              : " + ("REDUCED MOTION" if reduced else "normal"))
        print("villagers         : %d (%d awake, %d asleep)  SC=%.1f"
              % (len(vills), len(awake), len(asleep), SC))

        # ---------------------------------------------------------------- A
        # Structure. These hold with the cursor nowhere near the page, and they
        # are the ones that make the blink SAFE rather than merely untested: if
        # the lid is not inside the eyes group, a shifted eye and a blink land on
        # different pixels and the bug is invisible until a blink happens to fire
        # while the cursor is close - about once every 5.2s per villager.
        print("\n-- structure: a blink cannot land on the wrong pixels --")
        tot = js(ws, "document.querySelectorAll('#scene .bot .lid').length")
        inside = js(ws, "document.querySelectorAll('#scene .bot .eyes > .lid').length")
        check("every lid is a child of its eyes group", tot > 0 and tot == inside,
              "%s of %s" % (inside, tot))

        r = js(ws,
            "(()=>{const b=document.querySelector('#scene .bot');"
            "const eg=b.querySelector('.eyes');if(!eg)return 'MISMATCH no .eyes group';"
            "const pup=[...eg.children].filter(n=>n.tagName==='rect')"
            ".map(r=>r.getAttribute('x')+','+r.getAttribute('y')).sort().join(' ');"
            "const ld=[...eg.querySelector('.lid').children]"
            ".map(r=>r.getAttribute('x')+','+r.getAttribute('y')).sort().join(' ');"
            "return pup===ld?('lid sits exactly on the pupils at '+pup)"
            ":('MISMATCH pupils['+pup+'] lid['+ld+']');})()")
        check("lid rects are generated from the same cells as the pupils",
              "MISMATCH" not in str(r), r)

        # The pupils have ONE clay pixel of margin, which is why eye tracking was
        # cut. Measured off BOT rather than asserted, so if the sprite is ever
        # widened this check says so and the decision can be revisited.
        r = js(ws,
            "(()=>{const es=[],edge=[];"
            "for(let y=0;y<BOT.length;y++)for(let x=0;x<BOT[y].length;x++)"
            "if(BOT[y][x]==='o')es.push([x,y]);"
            "for(const ex of [-1,1])for(const e of es){"
            "const nx=e[0]+ex,ny=e[1];"
            "const l=(BOT[ny]||'')[nx-1],rr=(BOT[ny]||'')[nx+1];"
            "if(l===undefined||l==='.'||rr===undefined||rr==='.')"
            "edge.push('shift'+(ex>0?'+':'')+ex+' puts a pupil at '+nx+','+ny+' on the silhouette');}"
            "return edge.length?('ONE-PIXEL MARGIN: '+edge.join('; ')):'pupils have room to move';})()")
        print("  .... sprite margin: " + str(r))

        # POSITIVE CONTROL, run every time rather than trusted once. The whole
        # "eyes never move" section below is a claim that a detector stayed
        # silent, which is worth nothing unless the detector can speak. So
        # displace one eyes group for real, require the guard to catch it, and put
        # it back. The SVG transform ATTRIBUTE is used deliberately: it is the one
        # mechanism proven to move the group on this page, and it is immune to the
        # Content-Security-Policy that silently drops an injected <style>. That CSP is
        # real and was read, not assumed: coc.py:871 sends
        # "style-src 'nonce-<nonce>'", and only the page's own nonced <style>
        # carries that nonce, so script-injected CSS never applies.
        quiet = len(eyes_moved(ws))
        js(ws, "document.querySelector('#scene .bot .eyes')"
               ".setAttribute('transform','translate(1,0)')")
        time.sleep(0.2)
        fired = eyes_moved(ws)
        js(ws, "document.querySelector('#scene .bot .eyes').removeAttribute('transform')")
        time.sleep(0.2)
        after = len(eyes_moved(ws))
        check("POSITIVE CONTROL: the displacement guard fires when eyes do move",
              quiet == 0 and len(fired) == 1 and after == 0,
              "quiet=%d, with a 1px displacement=%s, restored=%d"
              % (quiet, fired or "NOTHING DETECTED", after))

        # The position gate sits AFTER the structural block on purpose. Those
        # three checks need no cursor and no stored position, so bailing before
        # them would hide real findings behind an unrelated prerequisite - which
        # is exactly what the first version of this file did.
        if info.get("noPos"):
            check("every villager has a stored screen position", False,
                  "%s of %s missing v.sx/v.sy" % (info["noPos"], info.get("total")))
        if not vills:
            print("\nPHASE 3: %d FAILED -> no villager carries a stored position, "
                  "the cursor checks cannot run" % len(FAILS))
            sys.exit(1)

        # ---------------------------------------------------------------- H
        if reduced:
            print("\n-- reduced motion: none of Phase 3 may run --")
            check("media query is live", js(ws, "RM.matches") is True)
            tgt = awake[0] if awake else vills[0]
            move(ws, tgt["ax"], tgt["ay"])
            move(ws, tgt["ax"] + 2, tgt["ay"])   # a second real move, still inside
            st = state(ws, tgt["id"])
            check("no eye offset written", st["ex"] in ("", "0px") and st["ey"] in ("", "0px"),
                  "ex=%r ey=%r" % (st["ex"], st["ey"]))
            check("no villager is greeting",
                  js(ws, "document.querySelectorAll('#scene .bot.greet').length") == 0)
            check("no sleeper has been woken",
                  js(ws, "document.querySelectorAll('#scene .bot.peek').length") == 0)
            # COUNTED, not sampled. `PROXRAF == 0` cannot fail: proxFrame() sets
            # it to 0 as its first statement and move() sleeps 0.14s, several
            # frames, so it reads 0 in normal mode too. Wrapping
            # requestAnimationFrame makes the claim "reduced motion schedules no
            # frame" actually falsifiable - before onMove() gained its own
            # RM.matches gate this counted one per mouse move.
            js(ws, "(()=>{window.__raf=0;const o=window.requestAnimationFrame;"
                   "window.requestAnimationFrame=function(f){window.__raf++;"
                   "return o.call(window,f);};})()")
            for dx, dy in ((0, 0), (3, 3), (-3, 0), (0, 5)):
                move(ws, tgt["ax"] + dx, tgt["ay"] + dy)
            n = js(ws, "window.__raf")
            check("four mouse moves scheduled no rAF at all", n == 0,
                  "requestAnimationFrame calls: %s (want 0)" % n)
            check("proximity holds no pending frame", js(ws, "PROXRAF") == 0)
            check("traffic rAF never started", js(ws, "RAF") == 0)
            offs = all_offsets(ws)
            check("not one offset anywhere on the page",
                  all(o == "|" or o == "0px|0px" for o in offs),
                  "distinct: " + str(sorted(set(offs))))
            print("\nPHASE 3 REDUCED: " + ("all checks passed" if not FAILS
                                           else "%d FAILED" % len(FAILS)))
            return

        # ---------------------------------------------------------------- B
        # THE EYES NEVER MOVE. The owner cut eye tracking after seeing it: "no need
        # for the eyes to get detached from the body". This is the regression
        # guard for that decision, and it is swept over every villager from four
        # directions and at four distances - a single-point check would pass
        # against a build that only detached the eyes at certain angles.
        check("the 30s poll is stoppable by a harness", pollable is True,
              "index.html must expose the `load` interval handle, e.g. `let POLL=`")

        print("\n-- the eyes never leave the face, from any cursor angle --")
        off = SC * 0.55
        seen, moved, slept = set(), [], 0
        probes = [(1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, -0.7)]
        for v in vills:
            for mul in (0.20, 0.55):
                for ux, uy in probes:
                    move(ws, v["ax"] + ux * SC * mul, v["ay"] + uy * SC * mul)
                    seen.update(all_offsets(ws))
                    moved.extend(eyes_moved(ws))
                    # ACCUMULATED inside the loop. Asking once after the sweep is a
                    # point-in-time query about the final cursor position and says
                    # nothing about the ~600 positions before it.
                    slept += sleepers_greeting(ws)
        check("no eyes group is ever displaced", not moved,
              "%d probes, displaced: %s" % (len(vills) * 12, moved[:4] or "none"))
        check("no --ex/--ey custom property is ever written",
              all(o == "|" for o in seen),
              "distinct values across the sweep: " + str(sorted(seen)))

        # ---------------------------------------------------------------- E
        # The sleeper scope, asserted across that same sweep: the wave must never
        # have appeared on a sleeper at ANY cursor position, not merely at the
        # one position a single-point test would try.
        print("\n-- sleepers: eyes open, no wave, and they still never move --")
        check("no sleeper greeted at ANY of the %d swept positions" % (len(vills) * 12),
              slept == 0, "greeting sleepers counted across the sweep: %d" % slept)

        if asleep:
            s = asleep[0]
            before = js(ws, "(()=>{const v=VILLS.get(" + repr(s["id"]).replace("'", '"')
                            + ");return [v.wx,v.wy,v.wz,v.el.style.transform];})()")
            move(ws, s["ax"] + off, s["ay"])
            st = state(ws, s["id"])
            after = js(ws, "(()=>{const v=VILLS.get(" + repr(s["id"]).replace("'", '"')
                           + ");return [v.wx,v.wy,v.wz,v.el.style.transform];})()")
            check("a near sleeper is marked peek", st["peek"] is True, st["cls"])
            check("its lid is OPEN while peeking", st["lid"] == "0",
                  "computed lid opacity %r" % st["lid"])
            check("its eyes open in place, not displaced",
                  st["eyeTr"] == "none" and st["eyeTl"] == "none",
                  "transform=%r translate=%r" % (st["eyeTr"], st["eyeTl"]))
            check("it is NOT greeting", st["greet"] is False)
            check("its wave arm stays invisible", st["wav"] == "0", "opacity %r" % st["wav"])
            check("the z's stop while it is awake",
                  js(ws, "getComputedStyle(document.querySelector("
                         "'#scene .bot.sleep.peek .zed')).opacity") == "0")
            check("SLEEPERS NEVER MOVE: position identical", before == after,
                  "%s -> %s" % (before, after))

            # ...and it goes back to sleep when the cursor leaves.
            move(ws, s["ax"] + SC * 3, s["ay"] + SC * 3)
            st = state(ws, s["id"])
            check("it falls asleep again once the cursor leaves",
                  st["peek"] is False and st["lid"] == "1",
                  "peek=%r lid opacity=%r" % (st["peek"], st["lid"]))
        else:
            print("  .... no sleeping villager on this scan, sleeper checks skipped")

        # ---------------------------------------------------------------- D
        print("\n-- the greeting wave --")
        if awake:
            a = awake[0]
            move(ws, a["ax"] + SC * 0.20, a["ay"])
            st = state(ws, a["id"])
            check("an awake villager under the cursor greets", st["greet"] is True, st["cls"])
            check("the wave arm is actually visible", st["wav"] == "1",
                  "computed .wav opacity %r" % st["wav"])
            check("the wave arm is animating", js(ws,
                  "getComputedStyle(document.querySelector('#scene .bot.greet .wav'))"
                  ".animationName") == "wavehand")

            # ------------------------------------------------------------ G
            # Hysteresis. Between the two rings the answer DEPENDS on which side
            # the cursor came from - that is the whole point of having two.
            print("\n-- hysteresis: the wave does not flicker on the boundary --")
            mid = SC * 0.55                      # between IN 0.50 and OUT 0.60
            move(ws, a["ax"] + mid, a["ay"])     # drifting outward from inside
            held = state(ws, a["id"])["greet"]
            move(ws, a["ax"] + SC * 3, a["ay"])  # right out of both rings
            move(ws, a["ax"] + mid, a["ay"])     # approach the same spot from outside
            fresh = state(ws, a["id"])["greet"]
            check("between the rings: kept when leaving, not started when arriving",
                  held is True and fresh is False,
                  "leaving=%r arriving=%r" % (held, fresh))

            # ------------------------------------------------------------ F
            # setLook() rewrites the class attribute and replaces the inner
            # markup. A greeter dispatched onto a trip is the case that proves
            # the state is held on the model and re-applied, not parked in the
            # DOM where a repaint destroys it.
            print("\n-- greeting survives setLook(), which rewrites class and markup --")
            move(ws, a["ax"] + SC * 0.20, a["ay"])
            before_cls = state(ws, a["id"])["cls"]
            js(ws, "(()=>{const v=VILLS.get(" + repr(a["id"]).replace("'", '"') + ");"
                   "v.trip=[{at:'home',dur:9000}];v.si=0;v.lastTo=null;"
                   "v.t0=performance.now();setLook(v);})()")
            time.sleep(0.2)
            st = state(ws, a["id"])
            check("greet survived the look change",
                  st["greet"] is True and st["mgreet"] is True,
                  "was %r, now %r" % (before_cls, st["cls"]))
            check("the wave arm survived the markup rebuild", st["wav"] == "1",
                  "opacity %r" % st["wav"])
            js(ws, "(()=>{const v=VILLS.get(" + repr(a["id"]).replace("'", '"') + ");"
                   "v.trip=null;v.si=0;setLook(v);})()")
        else:
            print("  .... every villager is dormant on this scan, wave checks skipped")

        # ---------------------------------------------------------------- far
        print("\n-- out of range --")
        move(ws, 4, 4)
        offs = all_offsets(ws)
        check("cursor in the corner: nobody tracks, nobody greets",
              all(o in ("|", "0px|0px") for o in offs)
              and js(ws, "document.querySelectorAll('#scene .bot.greet,"
                         "#scene .bot.peek').length") == 0,
              "distinct offsets: " + str(sorted(set(offs))))

        print("\nPHASE 3: " + ("all checks passed" if not FAILS
                               else "%d FAILED -> %s" % (len(FAILS), FAILS)))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
    if FAILS:
        sys.exit(1)


main()
