# apps/web — the UbuntuRemit client

Static HTML. **There is no build step.**

```bash
python3 -m http.server 5173 --directory apps/web
# http://localhost:5173  →  redirects to send-amount.html
```

| Page | Screen | Origin |
| --- | --- | --- |
| `index.html` | Redirect only — no UI of its own | written |
| `send-amount.html` | Send-money **step 1** — Amount | composed |
| `send-money.html` | Send-money **step 2** — Recipient | **Stitch export** |
| `send-compliance.html` | Send-money **step 3** — Compliance | composed |
| `send-review.html` | Send-money **step 4** — Review | composed |
| `compliance.html` | Compliance Health Dashboard | **Stitch export** |
| `wallet.html` | Wallet & History | **Stitch export** |

`send-money.html` keeps its filename despite being step 2 — renaming it would churn every existing
link for no user-visible gain.

## Two kinds of page, and the difference matters

**Exported** pages have a PNG in `legacy/stitch-mockups/`. That image is their specification: after
any edit, open the page beside it. They are otherwise unchanged from the export — `send-money.html`
differs by 11 `href` attributes and two `<button>`→`<a>` swaps (identical classes, so identical
rendering) needed for the flow to navigate. Nothing else.

**Composed** pages have **no PNG**. They were built from the design system and the vocabulary of the
exported pages — every element on them already exists on a shipping page, and their chrome (head,
header, rail, grid, right column) is copied byte-for-byte from `send-money.html` by script rather
than re-typed. Design: [`docs/design/send-money-wizard.md`](../../docs/design/send-money-wizard.md).

> ⚠ **The composed pages have not been visually verified.** The session that built them could not
> see its own output. Walking the flow beside step 2 is the outstanding check — see that design
> doc §2 and §9.

## Rules for changing this

1. **Exported pages: the PNG is the reference.** Open the page beside it, before and after.
2. **Composed pages: step 2 is the reference.** The chrome must stay identical across all four
   wizard steps — that's what makes the flow feel like one screen with changing content.
3. **Don't refactor.** Not into components, not into a framework, not into shared partials. The
   duplication across these files is deliberate. A rewrite is a design decision that goes through
   `docs/design/frontend-web.md` §8 first — one was already attempted and reverted.
4. **Don't restyle,** and don't invent components. Tokens live in each file's `tailwind.config`
   block; the rationale is `legacy/stitch-mockups/ubuntu_heritage/DESIGN.md`, still binding.
5. **Don't overclaim.** New copy may say "ISO 20022 message prepared"; it may not say "SARB
   compliant". See `docs/design/iso20022-messaging.md` §3.6.
6. Frontend lanes are Claude's by default — [../../AGENTS.md](../../AGENTS.md) §1.

## Known issues (real, tracked, not cosmetic)

| Issue | Why it matters | Task |
| --- | --- | --- |
| `cdn.tailwindcss.com` compiles Tailwind **in the browser** | Not a production mechanism, and a third-party script on every load of a settlement page | **T024** |
| Google Fonts + Material Symbols load from `fonts.googleapis.com` | Same problem — a sovereign-deployment product shouldn't phone out to render | **T024** |
| The avatar is a hot-linked `googleusercontent.com` URL | Will break; leaks a request per page view | **T024** |
| Forms hold no state; nothing submits | Expected — the services don't exist yet | **T025** |
| Figures are static | Expected, and honest: nothing claims to be a live rate | **T025** |
| Exported pages' copy overclaims ("Tier 1 banking protocols") | Conflicts with the conformance boundary, but editing the frozen export conflicts with rule 1 | **T032**, unresolved by design |
| Composed pages unverified visually | No PNG exists to check against | see above |
