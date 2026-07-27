# legacy/

Frozen source material. **Nothing here is built, served, or imported** — it is the reference the
live application is checked against.

| Path | What it is |
| --- | --- |
| `stitch-mockups/send_money_wizard/` | Step 2 (Recipient) of the send-money wizard — `screen.png` + the original Stitch `code.html`. |
| `stitch-mockups/compliance_dashboard/` | The Compliance Health Dashboard. |
| `stitch-mockups/wallet_history/` | Wallet & History. |
| `stitch-mockups/ubuntu_heritage/DESIGN.md` | The design system: "Institutional Warmth & The High-Performance Engine". |
| `stitch_send_money_wizard.zip` | The original export, kept intact. |

## Why it's kept

The screenshots are the **visual reference** every UI task in [TASKS.md](../TASKS.md) is specified
against, by path — per [docs/design-documentation.md](../docs/design-documentation.md) § UI is a
special case. "Build the compliance dashboard" invites an assistant to invent a compliance
dashboard; "build the one in `legacy/stitch-mockups/compliance_dashboard/screen.png`" does not.

The `code.html` files are the **origin of the shipping pages**: `apps/web/*.html` are copies of
them with nine `href` attributes wired up and nothing else changed. They are also the ground truth
for the **design tokens** — the `tailwind.config` block at the top of each carries the exact
Material-3 palette (`primary #164212`, `secondary #735c00`, the full `surface-container-*` ramp).

`ubuntu_heritage/DESIGN.md` is the *rationale* layer on top of those tokens — the no-line rule, the
glass-and-gold rule, tonal elevation, the forbidden patterns. It is still binding on new UI work;
it did not become legacy just because it sits in this folder.

## Rules

- **Don't edit these files.** They are a fixed reference; a moving reference is no reference.
- **Don't serve from here.** `apps/web/` is the UI that ships.
- If the design genuinely needs to change, change it in `apps/web/` and record the deviation in
  [docs/design/frontend-web.md](../docs/design/frontend-web.md) — don't retro-edit the mockup to
  match the code. That would destroy the only thing that makes a fidelity check possible.

## History

A React port of these three screens was built on 2026-07-27 and reverted the same day: it didn't
look like the PNGs. The export was already the approved design, so the port was risking the one
property that was correct in exchange for reuse nothing needed. The reasoning is in
[docs/design/frontend-web.md](../docs/design/frontend-web.md) §8 — read it before proposing
another rewrite.
