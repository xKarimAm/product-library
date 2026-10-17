# COC hive: villager movement and traffic

Design spec, 2026-09-10. Approved by the owner in conversation.

## Goal

Villagers currently stand on their own cell for life. The owner wants SimCity-style
life: they should move around and visit each other. He chose **all three traffic
types, layered** when asked whether trips should carry meaning.

COC's job, in the owner's own words, is three things at once: **morning triage**, an
**ambient status board** on a second screen, and a **context-switch launcher**. He
explicitly did NOT pick "something to show people". So movement has to earn its
place against those three jobs, not merely decorate.

Agency is settled and unchanged: **read-only over project folders, plus launch.**
COC may open VS Code and copy a resume command. It writes nothing into any project
folder and keeps no state of its own.

## Verified constraints

These were checked against the code, not assumed. Line numbers as of 2026-09-10.

| Fact | Where | Consequence |
| --- | --- | --- |
| No frame loop exists anywhere; all motion is CSS keyframes | only `setInterval(load, 30000)` at `index.html:1535` | movement introduces the app's first `requestAnimationFrame` loop |
| `layout()` wipes and rebuilds the villager layer | `index.html:1134` | a naive implementation teleports everyone home every 30s |
| Villagers are HTML divs in a single layer painted after all cells | `#scene` then `#bots` in the `<main id="hive">` markup | a villager can never be occluded by a nearer hut |
| Villager layer is `pointer-events:none` | `index.html:189` | villagers are not click targets today, and must not become them |
| The cell click handler resolves via `e.target.closest(".plaque")` | click handler in `index.html` | a villager inside `#scene` but outside a `.plaque` returns null and would silently close the bubble |
| `.bot.walk` leg cross-fade and body hop already exist and are verified | bot CSS block | the walk cycle is already built; only the old `stroll` pacing keyframe must be avoided |
| The sprite is bilaterally symmetric (eyes at columns 3 and 6, both 1.5 from the 4.5 centre; arms and both leg frames mirror) | `index.html:983-996` | horizontal flipping is a visual no-op; do not add it |
| `.bot.face .flipwrap` is dead CSS with no matching element | `index.html:270` | safe to delete |

## Phase 1: layer migration (no movement)

Ships and verifies on its own, with the village looking **identical** to today.

Villagers move from HTML divs in `#bots` into SVG groups inside the depth-sorted
`#scene`. Occlusion then falls out of the painter order that already works.

**Nesting preserves every existing animation.** Two nested groups:

```
<g class="bot MODE" style="transform: translate(SXpx, SYpx)">   <-- position, screen px
  <g transform="scale(PX) translate(-5,-9)">                    <-- sprite scale
    ... existing rects, arms, legs, props ...
  </g>
</g>
```

The outer group carries position in **screen pixels**, so every keyframe magnitude
(`bob` at `-2px`, `wave`, `hop` at `-1px`, the blink lid, all seven trades) keeps
working unchanged. The inner group carries the scale. The `translate(-5,-9)` puts
the sprite's origin at its **feet centre**, matching today's
`translate(-50%,-100%)` anchor.

Position is written as the CSS `transform` property; keyframes keep using the
independent `translate` property. The two compose, so they do not fight.

**Required:** `pointer-events: none` on the bot group, so clicks fall through to the
cell beneath and the launcher keeps working.

**Depth insertion.** Cells are already appended to `#scene` in painter order. A
villager is inserted after the last cell whose depth is at or below its own. Depth
is world `x + y`, the same quantity the existing cell sort uses. Re-insert only when
the bucket **changes**, never every frame.

**Also in this phase:** delete the dead `.flipwrap` rule.

### Phase 1 acceptance

- All seven trades plus sleep render exactly as before. Compare against the sprite
  sheet harness (`sheet.py`).
- Clicking a cell still opens the bubble. This is the launcher path; assert it.
- Villager groups carry `pointer-events:none`.
- Four widths (1600, 1280, 1024, 820): no truncation, no tile overlap, no label
  clash, nothing offscreen.
- Reduced motion still parks every sprite animation.
- `routes.py` passes: bubble, `/p/`, `/blocked`, `/plans`, search, Back.
- `coc.py` untouched, its selftest still green.

## Phase 2: the simulation

**Persistent model, rebuilt DOM.** Villager state lives in a module-level array that
survives `layout()`. Positions are stored in **world** coordinates, never screen
pixels, so a resize or the 30s poll re-projects everyone without disturbing a
journey. `layout()` recreates sprite elements, because the scene is wiped, but never
touches simulation state. Villagers are added or removed only when the project set
changes.

**Frame loop.** Idles itself out when nobody is walking; restarts on the next
scheduled trip. Never starts at all under `prefers-reduced-motion`, where everyone
stays home working.

**Trip states:** `WORKING` at home, `TRAVELLING` to a target, `DWELL` at the target,
`RETURNING`, then back to `WORKING` and its trade resumes.

### The three traffic types

**Wanderers.** Baseline ambience. A villager strolls to an adjacent cell in its own
comb, loiters, returns. Carries nothing. **Active cells only**: a sleeper that
wandered would contradict the dormancy signal, so the back comb never moves.

**Messengers.** Cells with `waiting_count > 0` dispatch a villager to the **front**
of the hive, toward the viewer, carrying a pennant. It waits there, then goes home.
On the current scan that is coc (2), Project Alpha (3) and Project Epsilon (1), six
decisions total. This is the ambient-board payoff: blocked work visibly comes to
your door, readable across the room with no click.

**Couriers.** Trace real context switches. Sort active projects by `last_activity`:
the most recent is the project you are in now, the one before it is where you came
from. A courier walks that edge carrying the violet load cube, which already exists
as the `carry` prop and its `load` group. When you switch projects the route changes
on the next poll, so ping-ponging becomes visible.

### Legibility guards

The owner flagged the busy-screen risk when choosing the layered option.

- Hard cap of **four** simultaneous travellers across all three types.
- Each type distinguishable at a glance: nothing carried, a pennant, or the violet
  cube.
- Walking pace slow enough to read: roughly one cell every 2.5 seconds.
- Sleepers never move.

### Phase 2 acceptance

- A villager's element actually changes position in the scene tree as its depth
  crosses a cell's. This is the **occlusion proof**, not a hope: assert element
  index ordering against cell groups.
- A journey survives both a resize and a 30s poll without teleporting.
- Sleepers never leave home.
- The four-traveller cap holds under forced scheduling.
- Reduced motion leaves the loop unstarted and everyone at home.
- Clicking a cell still opens the bubble while villagers are mid-walk.
- The Phase 1 battery still passes.

## Non-goals

Cut deliberately, and why.

- **Horizontal flipping to face the cursor.** Provably a visual no-op on a
  symmetric sprite, and flipping the whole SVG would mirror props, throwing a
  fisher's pond onto the wrong side of the plot.
- **Roads, carts, weather, mini-games.** None serve triage, glance, or jump-back-in.
- **Any write into a project folder.** Agency is settled: read-only plus launch.
- **Cursor proximity interaction** (eyes tracking, greeting, waking sleepers). A
  separate, smaller follow-on, designed and approved already in conversation; do it
  after Phase 2. Its design: one `mousemove` coalesced through rAF, compared against
  stored villager positions, two distance rings, eyes shifted by whole sprite pixels
  only, blink lid moved inside the eyes group so a blink cannot land on the wrong
  pixels, and the wave scoped away from sleepers so a woken villager does not wave
  in its sleep.
  **SHIPPED 2026-09-13. See "Phase 3" below - it is no longer a non-goal.**

## Phase 3, cursor proximity - shipped 2026-09-13

The six constraints above were the whole approved design. **One of them was cut
after it was built and seen.**

### Eye tracking is CUT, and it is not a tuning problem

Owner decision, 2026-09-13, looking at the working build: *"no need for the eyes to get
detached from the body but the rest of the interaction is cool."*

The constraint "eyes shifted by whole sprite pixels only" is unimplementable on
this sprite, and **the mechanism is not the obvious one.** The first version of
this section got it wrong; an independent reviewer found the real one.

`rects()` emits a rect only for `'#'` cells. `BOT` row 1 is `..#o##o#..`, so the
`.body` group paints clay at x=2,4,5,7 and **nothing at x=3 or x=6**. The eye
sockets are holes in the body, and the only paint covering them is the pupils
themselves, which live in `.eyes`. Translate `.eyes` by any non-zero amount and it
carries that paint away with it: **two background-coloured holes open in the middle
of the face.** That is what "detached from the body" actually was. It happens on
every non-zero offset, vertical ones included.

The wrong version said the defect was the pupil landing on the silhouette edge, and
defended the design with "every offset keeps both pupils on clay". That statement
is true, and it is about where the pupil **lands** while saying nothing about what
it **leaves behind** - and `phase3.py` encoded the same incomplete predicate, so
the harness agreed. A check derived from the same wrong model as the code cannot
catch the code.

Filling the sockets with clay in `.body` would close the holes and leave a second,
real problem: one clay pixel separates each pupil from the silhouette, so a
horizontal shift still puts it on the edge. Sub-pixel motion is a smear on
`crispEdges` pixel art, and widening the head changes the sprite the owner explicitly
kept when he rejected the three.js spike on 2026-09-13.

`tools/phase3.py` prints the margin it measures off `BOT` on every run:

```
.... sprite margin: ONE-PIXEL MARGIN: shift-1 puts a pupil at 2,1 on the
     silhouette; shift+1 puts a pupil at 7,1 on the silhouette
```

so if the sprite is ever widened, the line changes and the decision can be
reopened on evidence instead of memory.

**What shipped is the rest of the interaction**: the greeting wave, and a sleeper
that opens its eyes IN PLACE. The eyes group itself survives - see trap 16 - but
nothing ever transforms it.

**Radii are in SC units, not pixels.** SC is the hex radius and runs from 71 at
820px to 112.9 at 1600px, so a ring fixed in pixels would cover most of a cell at
one width and barely reach past a sprite at another. `fit()` already works in SC
for the same reason.

| Ring | Value | Effect |
|------|-------|--------|
| `R_LOOK` | 1.15 SC | a SLEEPER opens its eyes and its z's stop |
| `R_GREET_IN` | 0.50 SC | an awake villager starts waving |
| `R_GREET_OUT` | 0.60 SC | ...and keeps waving until the cursor passes this |

`R_GREET_OUT` is **hysteresis**, not a second feature. With one threshold a cursor
resting on the boundary flips `greet` on and off on consecutive frames, restarting
the wave keyframe from 0% each time - a twitch, not a wave.

**Sleepers: eyes open, no wave** (Owner decision, 2026-09-13). A sleeper inside `R_LOOK`
gets `.peek`, which lifts the held-shut lid and stops its z's. It is never inside
the greeting set at all, and **nothing in the feature writes a position**, so
"sleepers never move" is untouched rather than merely respected. It keeps snoring,
because a 1px breathing bob reads the same awake and leaving it alone means the
sleep pose is not modified at all. The rejected alternative was full inertness,
which loses the interaction, and full waking, which would make a dormant project
read as active on hover.

**The wave is its own limb, and a greeting is one pose for every trade.** `.wav` is
a new map drawn from the right shoulder upward, continuous with `armA`'s rows so it
reads as that arm raised. It is NOT a re-use of `armA`/`armB`: those cross-fade
under farm, swim and build and are pinned opaque under fish, paint and read, so
greeting through them would either fight a running keyframe or drop the hand a tool
is held in.

But `WAV` occupies (8,2) and (8,3), which are **`armB`'s own cells** - `ARM` is
drawn at `y0=2` for `armB` and `y0=4` for `armA`. On the trades that pin `armB`
visible, the wave rotated straight through a second, static right arm. Found by an
independent reviewer, not by the harness. Fixed by pinning the pose:

```css
.bot.greet .armA{animation:none;opacity:1}
.bot.greet .armB{animation:none;opacity:0}
```

`animation:none` is required on both, because a running CSS animation beats a plain
declaration in the cascade and `opacity` alone would lose to `frameA`/`frameB`.
**The cost, accepted:** for the 0.5-3s a villager greets, farm/swim/build stop
cross-fading and fish/paint show `armA` instead of the arm holding the rod or
brush. The tool itself lives in the `back`/`front` groups and is never touched. Two
right arms is the worse read. Verified by eye across all seven trades with
`tools/greetsheet.py`.

**Two traps this phase paid for, in the style of the list above.**

16. **The blink lid was a SIBLING of the pupils with its rects hardcoded at x=3
    and x=6.** The lid now lives INSIDE `.eyes` and is generated by the same
    `eyes()` scan as the pupils, in clay instead of ink, so the two cannot drift
    apart even if `BOT` is edited. This was found while building eye tracking -
    a shifted eye would have left the blink landing on vacated pixels - and it is
    **kept even though tracking was cut**, because the hardcoded coordinates were
    a latent bug in their own right: edit `BOT` and the blink silently stops
    covering the eyes, with nothing to catch it.
17. **`setLook()` rewrote the class attribute literally** (`"bot " + cls`), which
    erased any proximity class the moment a villager changed look - exactly what
    happens when a greeted villager is dispatched onto a trip. Both writers now go
    through `clsOf(v)`, and greet/peek live on the model, not the DOM. The same
    applies to `--ex`/`--ey`: they sit on the OUTER group beside `--delay` and
    `--blink`, because `setLook()` replaces the inner markup wholesale.

### Phase 3 acceptance

`tools/phase3.py`, normal and `--reduced`, 22 checks, all green 2026-09-13. Every
assertion is measured off a live page through CDP with a real
`Input.dispatchMouseEvent`, never by reading the source, and never by calling
`onMove()` directly - that would prove the arithmetic and skip the wiring.

- The lid is a **child** of `.eyes` on every villager, and its rects sit exactly on
  the pupils. Structural, so the blink is safe rather than untested.
- **The eyes never move.** 300 probes - every villager, six directions, two
  distances - and no `.eyes` group is ever displaced (`transform` and `translate`
  both compute to `none`) and no `--ex`/`--ey` is ever written. A single-point
  check would pass against a build that only detached the eyes at some angles.
- No sleeper carries `.greet` at any cursor position in that sweep. A near sleeper
  peeks, its lid computes to opacity 0, its z's to 0, its eyes stay undisplaced,
  and its world position and transform are **byte-identical** before and after.
- The greeting survives `setLook()`: measured going from `bot fish greet` to
  `bot walk greet` with the wave arm still at opacity 1 after the markup rebuild.
- Hysteresis: at 0.55 SC the answer depends on which side the cursor came from.
- `--reduced`: no offset written anywhere, no greet, no peek, and **four mouse
  moves schedule zero `requestAnimationFrame` calls** - counted by wrapping `rAF`,
  not by sampling `PROXRAF`. The same instrumentation counts 4 in normal mode, so
  the zero means something.

**The suite carries its own POSITIVE CONTROL, and it is the most important line in
it.** "The eyes never move" is a claim that a detector stayed silent, which is
worth nothing unless the detector can speak. So every run displaces one `.eyes`
group for real, requires the guard to catch it, and puts it back:

```
PASS POSITIVE CONTROL: the displacement guard fires when eyes do move
     quiet=0, with a 1px displacement=['3.00,0.00'], restored=0
```

3.00 is one sprite pixel at `scale(3)`. This exists because the FIRST version of
the guard read `getComputedStyle().transform` and could not have failed: it reports
`none` for an SVG `transform` attribute, and `none` for a rule the page never
received - and the Content-Security-Policy silently drops an injected `<style>`
(verified, not assumed: `coc.py:871` sends `style-src 'nonce-<nonce>'`, and only
the page's own nonced block carries that nonce), so
an attempt to test it "passed" while measuring nothing at all. The guard now
compares `.eyes`' `getCTM()` against its parent's, which catches a displacement
whatever put it there.

**The suite was negative-controlled**, which is the only reason to trust it: run
against `index_v7_phase2.html.bak` it reports 3 failures and exits 1. An earlier
version of the harness crashed with a `TypeError` there instead of reporting, and
bailed before the structural checks - both fixed, so a broken build reports every
finding it can reach.

No regression in the rest of the battery: `phase1.py` (242 occlusion checks, 0
violations), `phase2.py`, `phase2.py --reduced`, `msgcheck.py` at all four widths,
`routes.py`, `sheet.py`, `err.py`, and `shot.py` at 1600/1280/1024/820 plus
`--reduced` - no truncation, no tile overlap, no chip clash, nothing offscreen, all
trades shown. The sprite sheet renders identically to the pre-change build.

**On the animation count, because it moved and a moved number should be explained
rather than waved through.** `shot.py` read 243 normal / 50 reduced on 2026-09-10
and reads 280 / 53 now. None of that is this phase. It was checked by swapping
`index_v7_phase2.html.bak` in and re-measuring: the pre-change build reported the
same 264 / 52 as the new one did while the scan held 24 projects. The registry has
since grown to 25, which is where the rest comes from. `.wav` adds no animation
unless `.greet` is present, and a headless probe has no cursor.

`coc.py` is untouched at 61802 bytes, mtime 2026-09-09 14:44, so its `--selftest`
and `tools/mutate.py` still stand and were correctly not re-run.

### What an independent review changed

The diff went to a reviewer with fresh context, the files, and the invariants -
deliberately not the reasoning. It earned its keep. Acted on:

- **The real cause of the detached eyes** (above). The code was right; the comment
  explaining it was wrong, and a wrong explanation means the fix was never actually
  understood.
- **`.wav` collides with `armB`** at (8,2) and (8,3) (above).
- **Reduced motion still armed a rAF.** `onMove` scheduled a frame and only then
  `updateProx` checked `RM.matches`, so reduced motion booked one frame per mouse
  move before deciding to do nothing in it. The gate moved into `onMove`.
- **Three checks that could not fail.** `PROXRAF === 0` (zeroed by `proxFrame`
  before anything could read it), the sleeper-greet check (asked once **after** the
  sweep, so it described one cursor position out of 300), and the displacement
  guard itself.
- **The 30s poll had no handle.** `setInterval(load, 30000)` was anonymous, so no
  harness could stop it, and any run outlasting 30s had every villager node rebuilt
  mid-assertion. It is `let POLL` now, and `phase1`/`phase2`/`phase3` all clear it.
  This was **not** hypothetical: `phase2.py` failed "no traveller ever stood outside
  a cell" once on 2026-09-13 and passed on the next run with nothing changed. See
  trap 18.
- **Two comments that were simply false**: the `isConnected` guard is not about the
  search filter (`applyFilter` dims with `style.opacity` and removes nothing, so a
  filtered villager does still greet, at 13% opacity), and the page cannot scroll
  (`body` is `overflow:hidden` at `height:100%`, nothing calls `scrollTo`, and
  `scroll` does not bubble to `window`), so the scroll listener was dead code and
  is gone.

**Knowingly NOT acted on.** Listed in full, because a project whose whole point is
not dropping findings silently does not get to drop these either.

- **`anchors()` reproduces the implementation's own anchor formula** character for
  character, so the cursor is aimed wherever the code believes the eyes are and a
  wrong row or sign would move target and predicate together. This was the
  reviewer's second-highest finding and it mattered far more when eye tracking
  existed; with tracking cut, the formula only picks a point inside the rings, and
  the rings are 0.50-1.15 SC against an error that could only be a few sprite
  pixels. Worth fixing with an independent `getBoundingClientRect()` reading if
  anything ever depends on the anchor again.
- **The viewBox ratio conversion is untested** - `anchors()` works in raw pixels,
  so the `vb.width / r.width` factor in `updateProx()` has no coverage. It is 1:1
  today by construction.
- `updateProx()` forces one synchronous layout in `layout()`'s tail. The per-frame
  path is cached and clean; it is the layout tail that pays, once per resize and
  once per poll.
- It can run twice in a frame when a villager walks while the mouse moves. The
  second pass is write-free, since `setProx()` short-circuits.
- **`tick()`'s `updateProx()` call has no coverage**, because `park()` stops all
  movement before any check runs. That line exists so a walking villager tracks a
  stationary cursor.
- **No `blur` / `visibilitychange` handling**: only `mouseleave` clears `CUR_IN`,
  so a villager can be left greeting after the window loses focus.
- `clearProx()` in the RM change handler is redundant - `layout()` follows it
  immediately and replaces every node - and that handler does not clear `CUR_IN`.
- A peeking sleeper **does not blink** (`.bot.sleep .lid{animation:none}` still
  wins), and its z's take up to 1.86s to reappear after the cursor leaves, because
  removing `.peek` restarts `zfloat` from 0% with the villager's own `--delay`.
- `setLook()` restarts the wave keyframe, since it rebuilds the markup that holds
  `.wav`.
- **Harness nits**: the "cursor far away" probes move to `ax + SC*3`, which can
  leave the viewport rather than being a defined in-window empty point; `state()`
  has no null guard on `.wav` or the peeking `.zed`, so a missing element surfaces
  as a driver error instead of a named FAIL.
- The rings degenerate below about SC 12 (`R_LOOK*SC` falls inside the head), which
  needs a viewport far outside the four tested widths. Nothing enforces a floor.

18. **The 30s `load` poll is a flake source in every harness.** A suite that runs
    longer than 30s gets `layout()` called underneath it - `place()`, `fit()`, and
    every villager node replaced - between a measurement and the assertion about
    it. Stop `POLL` alongside `TRAFFIC` at the top of any new harness.

## Rollback

`index_v4_hive_crop.html.bak` is the hive with all seven trades and the crop and hat
fixes, immediately before this work. Earlier: `index_v3_hive.html.bak`,
`index_v2_iso.html.bak`, `index_v1_radial.html.bak`.
