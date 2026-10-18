# Demo day runbook

> Temporary: this file is for the live demo and will be removed from the repo afterwards.
> The full presenter guide is [DEMO.md](DEMO.md).

Product Library turns every project you've started with Claude Code into a SimCity-style city.
The demo runs on 20 made-up projects, so nothing personal is ever on screen.

## 1. Before you go on (10 minutes)

1. **Turn animations on.** Windows: Settings > Accessibility > Visual effects > **Animation effects On**.
   With it off, the browser asks for reduced motion and the city stands still.
2. **Rehearse** from the repo folder (about 30 seconds). It must print `rehearsal OK`:

   | Windows | macOS / Linux |
   |---|---|
   | `py demo/make_demo.py --rehearse` | `python3 demo/make_demo.py --rehearse` |

3. **Serve** the demo, then open http://127.0.0.1:7777 and press **F11** for full screen:

   | Windows | macOS / Linux |
   |---|---|
   | `py demo/make_demo.py --serve` | `python3 demo/make_demo.py --serve` |

   Want night (lit windows, searchlights, the blimp)? Open http://127.0.0.1:7777/?hour=22 instead.
4. Keep a **second terminal** open in the repo folder for the live moment.

## 2. The click path (about 8 minutes)

| # | Click | Say |
|---|---|---|
| 1 | Nothing yet: let the city move | "Every building is a project I started with Claude. Tents just started, towers have months of work, dirt lots never got going. Colour is state: clay is waiting on me, red is blocked." |
| 2 | **calculator** | "Gate PASS. The proof isn't a claim: it's the real test run and the commit." |
| 3 | **habit-tracker**, then **Full view** | "Someone committed after this note was written, so the note may be wrong. It's STALE and the gate fails." |
| 4 | Live moment (below) | "I change the code, the note doesn't change, Product Library notices." |
| 5 | **pomodoro-timer** | "It cites a commit that was never made. Product Library asked git." |
| 6 | **chatbot-frontend**, then **invoice-parser** | "Every building says who it's for and why it matters. This quote checks out word for word; the tallest tower's quote doesn't." |
| 7 | **calculator > Full view** | "How it started, where it is now, every session as a chapter titled by Claude, and what shipped." |
| 8 | **Report** in the header | "Every project, failing first, each with the one question to answer next." |

## 3. The live moment

In the second terminal:

    py demo/make_demo.py --commit calculator        # python3 on macOS/Linux

Wait about 10 seconds, press **F5**: calculator turns STALE with a dashed outline and gate FAIL. Repair it:

    py demo/make_demo.py --checkpoint calculator

Press **F5**: back to PASS, and the proof now cites the new commit.

## 4. If something goes wrong

- **City not moving:** animation effects are off (step 1.1). Reload after turning them on.
- **"could not clear ... coc-demo":** a server, terminal or Explorer window is still inside the demo folder. Close it and run the command again.
- **Port 7777 in use:** another copy is running. Stop it, or use another port: `$env:COC_PORT=7788` (PowerShell) before `--serve`.
- **`--commit` didn't flip it:** wait the full ten seconds before F5.
- **`demo check FAILED`:** the message names the product and field; rebuild with `--serve`.
