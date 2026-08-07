# Design System Strategy: Institutional Warmth & The High-Performance Engine

## 1. Overview & Creative North Star: "The Digital Diplomat"
This design system rejects the cold, sterile aesthetic of traditional fintech in favor of **"The Digital Diplomat."** Our Creative North Star bridges the gap between the immovable reliability of a Tier 1 Central Bank and the organic, community-driven spirit of Pan-African commerce. 

We break the "template" look by moving away from rigid, boxed grids. Instead, we use **Intentional Asymmetry** and **Tonal Depth**. Layouts should feel editorial—incorporating generous white space (using our 16 and 20 spacing tokens) and overlapping elements that suggest a sophisticated, layered intelligence rather than a flat, automated process.

## 2. Color: The Tonal Landscape
We use color to signal "Security" without the aggression of high-contrast borders. Our palette is rooted in the earth (Greens) and prosperity (Gold), stabilized by the technical precision of Slate Gray.

### The "No-Line" Rule
**Explicit Instruction:** Do not use 1px solid borders to define sections. Boundaries must be defined solely through background color shifts. For instance, a transaction list in `surface-container-low` should sit directly on a `surface` background. The change in hex value is the boundary.

### Surface Hierarchy & Nesting
Treat the UI as a physical stack of premium materials.
- **Base Layer:** `surface` (#f9f9f8).
- **The Workhorse:** `surface-container` for primary content areas.
- **Nested Focus:** Use `surface-container-highest` for high-priority compliance modules or "Verifying" states to pull them toward the user.

### The "Glass & Gold" Rule
To elevate the experience beyond "standard app," use Glassmorphism for floating action sheets or top navigation bars. Apply `surface-lowest` with a 70% opacity and a 20px backdrop-blur. 
- **Signature Gradient:** For primary CTAs (e.g., "Send Funds"), use a subtle linear gradient from `primary` (#164212) to `primary-container` (#2E5A27) at a 135-degree angle. This adds "soul" and depth that a flat hex code cannot achieve.

## 3. Typography: Editorial Authority
We pair the geometric precision of **Manrope** for high-level branding with the utilitarian clarity of **Inter** for transactional data.

- **Display & Headlines (Manrope):** Use `display-lg` to `headline-sm` for hero moments and section headers. These should be set with tighter letter-spacing (-0.02em) to feel "heavy" and authoritative, like a financial broadsheet.
- **The Engine (Inter):** All remittance data, exchange rates, and compliance statuses must use `body-md` or `label-md`. 
- **Hierarchy of Trust:** Use `title-lg` in `primary` color for success states, and `label-sm` in `on-surface-variant` for "ISO 20022 Verified" metadata.

## 4. Elevation & Depth: Tonal Layering
Traditional shadows are too "web 2.0." We achieve depth through **The Layering Principle**.

- **Ambient Shadows:** When a card *must* float (e.g., a modal or a primary transaction card), use a shadow with a blur of 40px and an opacity of 4%. The shadow color must be a tinted version of `on-surface` (#191c1c), never pure black.
- **The "Ghost Border" Fallback:** If a container lacks contrast against its background, use a "Ghost Border": the `outline-variant` token at 15% opacity. It should be felt, not seen.
- **Depth through Blur:** Use backdrop-blur on `surface-variant` elements to allow the rich earthy greens of the background to "bleed" through, softening the interface and making it feel like a unified ecosystem.

## 5. Components: Precision Primitives

### Buttons
- **Primary:** Gradient-filled (`primary` to `primary-container`), `xl` (1.5rem) roundedness. 
- **Secondary:** `surface-container-highest` background with `on-primary-fixed-variant` text. No border.
- **Tertiary:** Text-only using `primary` color, strictly for "Cancel" or "Back" actions.

### Cards & Lists
**Strict Rule:** Forbid divider lines. Separate list items using the `2` or `3` spacing scale (0.5rem - 0.75rem) or by alternating subtle background shades (`surface-container-low` vs `surface-container-lowest`).
- **Compliance Badges:** Use `secondary-container` (Gold) for "Pending" and `primary-fixed` (Light Green) for "Verified." Shapes must be Pill-style (`full` roundedness).

### Inputs & Fields
- **Container:** Use `surface-container-high`. 
- **Focus State:** Instead of a thick border, use a 2px "Ghost Border" of `primary` at 40% opacity and a subtle interior glow.
- **Verification Icons:** All "ISO 20022" icons should be rendered in `secondary` (Rich Gold) to signal institutional value.

### Contextual Components (The "Compliance Engine")
- **The Progress Ribbon:** A non-linear, organic stepper that uses `surface-dim` for inactive stages and a glowing `primary` for the active compliance check.
- **The Trust-Shield Overlay:** A glassmorphic card that appears during "KYC" processing, utilizing `backdrop-blur` to keep the user grounded in the app while the engine works.

## 6. Do’s and Don’ts

### Do
- **Do** use `xl` (1.5rem) corner radii for main containers to convey "Community Connection" and approachability.
- **Do** use `manrope` for large numerical values (Exchange Rates). It feels more "premium bank" than Inter.
- **Do** allow elements to overlap slightly (e.g., a "Verified" badge breaking the top edge of a card) to create a custom, high-end feel.

### Don’t
- **Don’t** use 100% black (#000000) for text. Always use `on-surface` (#191c1c) to maintain the "Earthy" tonal warmth.
- **Don’t** use standard "Success Green" (#00FF00). Only use our `primary` (#164212) or `primary_fixed_dim` (#a1d493) to maintain the "Institutional" vibe.
- **Don’t** use shadows on every card. If everything floats, nothing is important. Rely on background shifts first.