# COC city: skyscrapers and the SimCity merger

POC built 2026-09-22. Feature set approved by the owner 2026-09-23.

## What this is

The owner: *"can we start making the buildings into sky scrapers, and also have a list
of all the projects on the right, like a small drop down menu. also, I want this to
be a merger with something like sim city, like there is construction going on,
someone is farming, so our animations and models are fine, just build on top of it,
give me a poc and then lets build on top of it."*

So: the villagers, trades, traffic and hex combs all stay. The buildings change, and
the city gains SimCity chrome on top. Nothing is replaced.

## POC, shipped 2026-09-22

`poc_city.html` at the repo root. **Standalone** - real project data is baked in, so
it opens from `file://` with no server and no token. `index.html` and `coc.py` were
NOT touched; the POC is generated from `index.html` by `tools/build_poc.py`, so it
can always be rebuilt from the current deliverable.

```
py tools/build_poc.py          # rebuild poc_city.html from index.html + poc_data.json
py tools/pocprobe.py           # measure the skyline; exits 1 on bad geometry
py tools/poczoom.py 2.1        # magnified capture for judging by eye
```

**Huts became skyscrapers.** Three setback tiers, window grids on both visible
faces, a parapet band, a flat roof. Height is `sessions*4 + prompts.length`,
log-scaled. Windows are lit by recency: live amber, this-month dim amber, dormant
dark. The lit/dark pattern is a deterministic function of row, column and project
id - **never `Math.random`**, because `layout()` repaints every cell twice a minute
and a random pattern would shimmer.

**The roof colour survived, on the parapet.** It was the pitched roof's job and it
still means the same thing: clay = a decision waiting on you, red = blocked, violet
= live session-state, blue = git branch, green = transcripts only.

**Construction is real state, not decoration.** An ACTIVE project with a live
session-state file draws its top tier as bare girders with a swinging tower crane
over it - this block is still going up. Five on the 2026-09-22 scan. Other live
projects get an antenna and a blinking beacon.

**Roster panel** on the right: a collapsible `<details>`, waiting-on-you first then
most recent, state dot + flag + age, click opens that project's bubble.

### Two things the POC got wrong first, both worth keeping written down

**One height cap for every tier inverted the hierarchy.** A dormant folder with 30
old sessions grew a taller, brighter tower than a project worked on that morning,
so the skyline argued against the roof colour, the villager pose AND the comb the
cell sits in. Caps are per tier now: live 1.55, this-month 0.85, dormant 0.26.
Downtown is the live comb; dormant stays low-rise dark blocks however much history
it holds.

**`p.prompts` is an ARRAY of prompt strings, not a count.** `sessions*4 + p.prompts`
string-concatenates, `Math.log10` of that is `NaN`, and an SVG polygon with `NaN` in
its points draws nothing and raises nothing. Eleven of thirteen live towers were
invisible while `shot.py` reported "no errors, no tile overlap, nothing offscreen" -
none of its checks look at whether a building has extent. The dormant towers looked
correct only because an empty array concatenates to a number that happens to be
plausible. A name is not a behavior: the field is called `prompts` and holds prose.

`tools/pocprobe.py` now counts `NaN` polygons and towers under 10px and exits 1, and
`drawHouse` falls back to the tier base with a `console.warn` if the height is not
finite. **A tower that is wrong is a bug you can see; a tower that is absent looks
like a design choice.**

## Built 2026-10-14: the four mechanics and the right rail

All five approved items are built into `tools/build_poc.py`; `index.html` and
`coc.py` remain untouched (115922 / 61802 bytes). `tools/poc_data.json` was
re-fetched from the live server on 2026-10-14 - 34 projects, 18 grey stubs (the
spec below says 14; that was the 2026-09 scan). The 2026-09-22 scan is kept as
`tools/poc_data_2026-09-22.json`. **Re-fetch before judging the POC**: `tier()`
measures age against `Date.now()`, so baked data ages - by 2026-10-14 the frozen
scan had no project inside 7 days and the live comb would have rendered empty.

Every string splice in the build now goes through `splice()`, which asserts its
anchor occurs exactly the expected number of times. A bare `str.replace` on a
drifted anchor is a silent no-op that ships a POC with a mechanic missing; the
guard caught one ordering mistake during this build. The one exception is the
`drawHouse` replacement, which slices by `src.index()` and so still fails loudly
(ValueError) on a missing anchor.

`py tools/pocprobe.py` runs 53 checks across all mechanics, four of them
CONTROLS that plant the defect a check exists for and require the check to catch
it: the night window rule removed, a truck with no depth bucket, a rail collapse
that never re-runs `layout()`, and a `fit()` that ignores the meter. If a control
ever passes trivially, the run fails. It sets the VIEWPORT with
`Emulation.setDeviceMetricsOverride`, because `--window-size=1600,1000` measured
1582x904. It derives every expectation independently of the page's own helpers
(see "Independent review" below for why).

**Right rail.** `#app` is a two-column grid under the header; the rail is an
`<aside>` in column 2 and `#hive` gets column 1, so `fit()` simply sees the
narrower `hive.clientWidth`. The list is `flex:1; min-height:0` and scrolls, which
fixed the clipped last row. The legend moved into the rail footer (fixing "legend
overlaps the front comb"). Collapsing to 44px waits for the width transition's own
`finished` promise and then calls `layout()` - a fixed backstop timer was tried
first and laid the city out 1px off when it fired before a slow transition ended.
The rail costs 268px of width. Measured in a 1582x904 viewport (what
`--window-size=1600,1000` actually gives): SC 89.8 -> 80.0. **The city is
height-bound there**, so collapsing the rail widens the hive (1314 -> 1538px)
and re-lays the comb but does not raise SC. Narrower cells made front-row meta lines collide
(they already touched at 1600 before the rail), so `dropMetaClashes()` now removes
a meta line wherever it actually overlaps another label - measured, not
thresholded, because the meta text is live data (trap 12). 2 of 7 survive at 1600.

**Power grid.** `isLot(p)` is `roofOf(p) === "#7C6E92"` - keyed off the colour
function itself so the lot and the grey it replaces cannot disagree. A lot is a
furrowed dirt plot with dashed zoning stakes where the tower would stand, plus a
dead streetlight in the silo-yard spot (empty for exactly these projects). Drawn
as `.lot`, never `.hut`, so the "tower under 10px" check does not misfire. **The
sleeping villager stays on its lot** - the spec was silent; decision recorded, ask
the owner if it should go. On the 2026-10-14 scan all 18 lots are also the 18 dormant
projects, which is coincidence-shaped (2026-09-10 had 14 grey vs 13 asleep).

**Day/night.** Four palettes (night, dawn, day, dusk) on local-clock keys
`0/5 night, 6.5 dawn, 8.5-16.5 day, 18.5 dusk, 20.5 night`, interpolated in sRGB.
DAY is the original palette value for value. `applySky()` writes `--ground-*`,
`--side-l/r`, `--slabtop`, `--top-a/b` (the cell-top gradient stops, reached via
the CSS `stop-color` property) and `--tod-glow` onto `#hive`; it runs from
`layout()`, so the 30s poll advances it with no timer of its own. Night lights
every window via `#hive[data-tod="night"] #scene .hut .win` - two ids, so it beats
`#scene .hut.cold .win` (1,3,0) on id count. Force an hour with `?hour=21` or
`window.POC_HOUR = 21; applySky()`.

**Roads and vehicles.** Two avenues on lines of constant depth `x+y` (screen-
horizontal in this projection): one in the band gap, one in front of the live
comb (`fit()` reserves `ROAD_REACH` below the live comb for it). A vehicle never
changes depth, so it takes one `bucketOf()` insertion per trip - the villagers'
depth-bucket rule. Pixel-art car and truck sprites, mirrored when heading left,
headlights lit at night. **Signal, not ambience:** cars run between live-comb
projects touched in the last 24h (half the time the real last switch, recent[1] ->
recent[0]), up to `min(3, stops - 1)`; trucks run supply trips from an avenue end
to construction sites (`_t === 1 && has_state`, the crane test), up to 2.
Endpoints are project ids resolved live every frame. Spawning runs inside
`dispatch()` after its reduced-motion gate; stepping runs inside `tick()`; the RM
change handler drops every vehicle. One interval, one rAF loop: clear `TRAFFIC`
and every vehicle finishes and `RAF` returns to 0 (measured, 13.7s).
`spawnVehicle(kind, from, to)` is exposed for probes.

**RCI meter.** Bottom-left of the hive: W / A / D bars are DISJOINT project counts
(waiting on you; otherwise not dormant; the rest), so they sum to the project
total. POP is total sessions. A clock line shows the hour and phase.

Probe trap paid for this session: `load()` arms `TRAFFIC` 3s after the first
render. A probe that clears it any earlier clears a 0 handle and the dispatcher
starts anyway - every vehicle check then races live spawning. `pocprobe.py` now
waits for `TRAFFIC !== 0` before clearing.

### Independent review, 2026-10-14

A fresh-context QA agent (council-qa) mutation-tested the probe. Of 18 defects
planted in scratch copies of `build_poc.py`, 11 still passed the first 36-check
probe, including `isLot = () => false`, which switches the power grid off
entirely. The cause was the same every time: the probe built its EXPECTED value
with the page's own helper (`PROJECTS.filter(isLot)`, `D = total - W - A`, a
direct `applySky()` call), so it agreed with any bug in that helper.

Fixed after the review:
- The probe was rewritten to derive expectations independently. Lots come from
  `poc_data.json` in Python. Meter bars come from raw `last_activity`. The clock
  is advanced through `layout()`. The probe now covers vehicles across
  `layout()`, `dispatch()` spawning, road count, `?hour=`, day window colours,
  NaN in `transform`/`cx`/`cy`, and reduced motion from first paint, counting
  every `requestAnimationFrame` call.
- **The meter covered the newest project's cell** at 1600x1000, 1920x1080 and
  1440x900. `fit()` now tests each cell's box against the meter and, only on a
  hit, re-solves with a left gutter, a bottom margin, or both, keeping the
  largest SC. Cost: SC 89.8 -> 83.4 at 1600x1000 and 104.4 -> 98.6 at 1920x1080.
  At 1440x900 and below it costs nothing.
- **A re-slot snapped a moving car 138px sideways.** `relayoutVehicles()` now
  rebases the current moving leg from the car's actual position (a linear leg to
  the live destination) on EVERY `layout()`, including the 30s poll and resizes.
  There is no re-slot detector; rebasing when nothing moved is a no-op apart from
  dropping the ease-in. It is the vehicle twin of the villagers' carried delta.
- **Reduced motion scheduled one rAF** (`buildRoster`'s first re-layout). It is
  now synchronous. The caret's rotate transition is now also off under reduced
  motion.
- **Every 30s poll reset the rail's scroll position and keyboard focus.** Both
  are now kept.
- A non-finite `POC_HOUR` painted `#NaNNaNNaN`; it is now guarded with `isFinite`.
- `splice()` asserts an exact anchor count; the build prints real on-disk bytes.

Named risks, NOT fixed (decisions or minor, recorded so they are not rediscovered):
- **The baked page carries every `/api/projects` field**, including `prompts`,
  `next_action`, `note`, `path` and `session_id`, in a file that needs no token
  to open. This predates today (the 2026-09-22 POC did the same). Do not share
  `poc_city.html`.
- A vehicle whose destination project leaves the scan is dropped within a frame
  rather than sent back, unlike villagers, which retarget home.
- Two rail toggles 80ms apart lay the city out once at a mid-transition width.
  The end state is correct.
- The header's "4 waiting on you" counts decisions; the meter's W=3 counts
  projects. "Active this week" (7) is not the meter's A (13, active this month).
  They measure different things on purpose, but the two could confuse a reader.
- At 901px the rail takes 268px of a 901px window (SC 25.3, below the 28.9 at
  899px, where the rail is hidden).
- The meta-clash check would also pass if every meta line were dropped.
- Depth-bucket coverage depends on a dormant comb existing; with no dormant
  projects there is no gap avenue and no truck check.
- The sheet routes (`/p/...`) throw a SecurityError from `pushState` on
  `file://`. This predates today's work.
- **`tools/drive.py` leaks headless Chrome.** `proc.terminate()` kills only the
  launcher process, so the renderer and GPU processes outlive every probe run.
  On 2026-10-14, 262 of them had accumulated, and the contention made the probe's
  CDP calls time out. Before blaming the page for a CDP timeout, count the
  processes whose command line contains `cprof_` and stop them; never stop the
  user's own Chrome. Fixing it would mean killing the process tree in `drive.py`,
  which every harness shares, so that is a separate change.
- `no_road_reach` survives mutation: the front avenue fits inside the 26px padding
  even without `ROAD_REACH`, so the reserve is a safety margin that nothing
  currently measures.

## The four mechanics as approved (2026-09-23), kept for reference

The owner picked all four on 2026-09-23. Ordered by payoff per unit of work.

### 1. Day/night cycle
Scene tint follows the real clock: dawn amber, midday flat, dusk purple, night dark
with every window lit. The windows already exist, so this is mostly a palette ramp
over the existing CSS variables plus a lit/dark override at night. Biggest visual
payoff for the least code, and it is what makes an ambient second-screen board feel
alive across a whole working day.

### 2. Roads and vehicles
Draw road tiles between cells and run trucks and cars on them. Couriers ALREADY
model real context switches - the project you were in, then the project you are in
now, by `last_activity` - so traffic density becomes a genuine signal of how much
you are ping-ponging between projects. Reuse the Phase 2 world-coordinate model and
the existing rAF loop; do not start a second one.

### 3. Power grid, which also settles the grey-stub decision
The 14 registry stubs that draw a grey roof because they have zero transcripts, no
session-state and no branch become **UNPOWERED EMPTY LOTS**: a dirt plot, no
building, a dead streetlight. This closes the backlog decision the owner has been
blocked on since 2026-09-09 without folding them into one counted cell and without
filtering them out - they read as *zoned, never built*, which is exactly what they
are. Fewer towers competing for attention, and the lots still carry their labels.

### 4. RCI demand meter and population
SimCity's bottom-left meter, re-mapped: waiting-on-you / active / dormant as three
bars, plus a population counter driven by total sessions. Pure triage chrome - it
says where to look before you read a single label.

## Approved next: the roster panel

The owner: *"the drop down list is kinda wierdly put. lets align it better and move
things around more dynamically."*

Redock it from a floating overlay into a proper **right rail**: full height, aligned
to the header, with `#hive` shrinking to the remaining width so the city reflows
around it rather than being covered by it. `fit()` already works in SC units off
`hive.clientWidth`, so handing it the reduced width is the whole mechanism - the
hive re-solves its own scale and the skyline re-lays out. Collapsing the rail must
animate and re-run `layout()` so the city grows back into the space.

## Known rough edges in the POC, not yet fixed

- FIXED 2026-10-14: the roster list clipped its last row (rail redock).
- Front-row towers sit partly behind their own label chip. Labels outrank scene
  content by design - trap 9 - so this needs a decision, not a bug fix.
- FIXED 2026-10-14: the bottom legend overlapped the front comb (moved to the rail).
- Cranes read faint at 1600px.
- The meter covers the left end of the front avenue. No car reaches it - cars
  stop at project columns - but the asphalt runs under the panel.
- With the rail open at 1600x1000 only 2 of 7 front-row meta lines survive the
  clash pass.
- `tools/poc_data.json` is a frozen scan (2026-10-14, 34 projects). Re-fetch it from
  `/api/projects` with the `X-COC-Token` header (read the token out of the served
  page) when the POC should show current data.

## Rollback

The POC is a generated file. Delete `poc_city.html` and nothing is lost; rebuild it
with `py tools/build_poc.py`. `index.html` remains the deliverable and is untouched
at 115922 bytes, `coc.py` at 61802 bytes, so `--selftest` and `tools/mutate.py` still
stand.
