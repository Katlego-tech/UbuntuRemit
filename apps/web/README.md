# apps/web — the UbuntuRemit client

Static HTML, exactly as exported from Stitch. **This is the UI. There is no build step.**

```bash
python3 -m http.server 5173 --directory apps/web
# http://localhost:5173  →  redirects to send-money.html
```

| Page | Screen |
| --- | --- |
| `index.html` | Redirect only — no UI of its own |
| `send-money.html` | Send-money wizard, step 2 (Recipient) |
| `compliance.html` | Compliance Health Dashboard |
| `wallet.html` | Wallet & History |

## What was changed from the export

**Nine `href` attributes, and nothing else.** The nav links pointed at `#`; they now point at the
sibling pages so the three screens work as one app. No markup was restructured, no class was
touched, no copy was edited. The rendered pixels are identical to
`legacy/stitch-mockups/*/screen.png`.

Links that are still `#` are the ones with no page behind them — **Dashboard**, **Settings**,
**Support**. They stay dead on purpose rather than pointing somewhere invented; see
[../../docs/design/frontend-web.md](../../docs/design/frontend-web.md) §10.

## Rules for changing this

1. **The screenshots in `legacy/stitch-mockups/` are the reference.** After any edit, open the page
   beside its PNG. If they differ, the page is wrong.
2. **Don't refactor it.** Not into components, not into a framework, not into shared partials —
   the duplication across the three files is deliberate for now. A rewrite is a design decision
   that goes through `docs/design/frontend-web.md` first, with agreement, not a passing cleanup.
3. **Don't restyle.** The token values live in each file's `tailwind.config` block and the
   rationale in `legacy/stitch-mockups/ubuntu_heritage/DESIGN.md`, which is still binding.
4. Frontend lanes are Claude's by default — [../../AGENTS.md](../../AGENTS.md) §1.

## Known issues (real, tracked, not cosmetic)

| Issue | Why it matters | Task |
| --- | --- | --- |
| `cdn.tailwindcss.com` compiles Tailwind **in the browser** at runtime | Not a production mechanism, and it's a third-party script on every load of a page handling settlement data | **T024** |
| Google Fonts + Material Symbols load from `fonts.googleapis.com` | Same problem — a sovereign-deployment product shouldn't phone out to render | **T024** |
| The avatar is a hot-linked `googleusercontent.com` URL | Will break; also leaks a request per page view | **T024** |
| Forms hold no state; nothing submits anywhere | Expected — the services don't exist yet | **T025** |
| Figures are the mockup's static values | Expected, and honest: nothing here claims to be a live rate | **T025** |

T024 is self-hosting the three external dependencies — a mechanical change with **no visual
effect**, and it should be verified against the PNGs like anything else. T025 is wiring the pages
to real endpoints once Phase 3 lands.
