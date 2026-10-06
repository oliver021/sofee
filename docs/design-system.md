# Design System

Every value Sofee renders. These numbers are measured, not guessed — the
contrast ratios below were computed against each palette's own background.
Do not adjust a hex without recomputing the column next to it.

Behaviour lives in `ux-foundations.md`. This document owns appearance only.

---

## 1. Token contract

Six palettes. One contract. A component never knows which palette it is in.

| Token          | Role                                                       |
| -------------- | ---------------------------------------------------------- |
| `--p-bg`       | Page ground                                                |
| `--p-surf`     | Raised surface (composer, panels, cards)                   |
| `--p-surf-2`   | Surface on surface (hover, nested)                         |
| `--p-ink`      | Body text                                                  |
| `--p-mut`      | Secondary text, icon rest state                            |
| `--p-acc`      | Primary accent                                             |
| `--p-acc2`     | Secondary accent — gradients, the second half of a ring    |
| `--p-line`     | Hairline at rest                                           |
| `--p-line-2`   | Hairline emphasised                                        |
| `--p-hi`       | Inner top highlight                                        |
| `--p-glow`     | Focus halo                                                 |
| `--p-display`  | Display typeface for this palette                          |
| `--p-dot`      | Dotted field gradient                                      |
| `--p-dot-size` | Dot grid pitch                                             |
| `--p-dot-mask` | Falloff mask for the dotted field                          |
| `--p-grad`     | Ambient gradient layers                                    |
| `--p-blend`    | Blend mode for the gradient layer (only Overprint uses it) |

Semantic colours — success, warning, critical — are a **separate scale** and are
never the accent. The context meter uses them; the accent must not.

A literal colour in a component fails lint. No exceptions.

---

## 2. The palettes

Applied via `data-palette` on `<html>`. Persisted per user. Default: **nocturne**.

### A · Nocturne — `nocturne`

Dark, luminous, glass. Violet bloom top-left, cyan ember bottom-right.
Display: **Sora**.

| Token  | Hex       | Contrast on ground |
| ------ | --------- | ------------------ |
| `bg`   | `#07080F` | —                  |
| `surf` | `#0E1020` | 1.06 : 1           |
| `ink`  | `#D2D5E8` | 13.73 : 1          |
| `mut`  | `#7A7F9E` | 5.10 : 1           |
| `acc`  | `#7B6BF5` | 5.01 : 1           |
| `acc2` | `#3FD9E4` | 11.67 : 1          |

### B · Overprint — `overprint`

Light, printed, flat. Risograph: two inks overprinting in `multiply`, no glow,
no glass. Display: **Familjen Grotesk**.

| Token  | Hex       | Contrast on ground |
| ------ | --------- | ------------------ |
| `bg`   | `#E9E8E3` | —                  |
| `surf` | `#F4F3EF` | 1.10 : 1           |
| `ink`  | `#191A15` | 14.26 : 1          |
| `mut`  | `#63645B` | 4.88 : 1           |
| `acc`  | `#2438C9` | 6.89 : 1           |
| `acc2` | `#F2568F` | **2.63 : 1**       |

`acc2` is graphic ink and button fill only — never text, never an icon that
carries meaning alone. The only palette with a light ground, so it sets the
contrast floor for every icon in the system.

Overprint-only tokens: `--p-blend: multiply`, `--p-cast: 3px 3px 0 rgba(36,56,201,.22)`
(a hard cast shadow — print does not blur), and a title gradient that stops at
`acc` rather than running into `acc2`.

### C · Tidepool — `tidepool`

Dark, matte, warm. Deep petrol with old gold; light enters from below like
light on water. Display: **Fraunces**.

| Token  | Hex       | Contrast on ground |
| ------ | --------- | ------------------ |
| `bg`   | `#08171B` | —                  |
| `surf` | `#0F262C` | 1.16 : 1           |
| `ink`  | `#D7E4E2` | 14.00 : 1          |
| `mut`  | `#70908F` | 5.29 : 1           |
| `acc`  | `#DFAE54` | 8.98 : 1           |
| `acc2` | `#4FA8A0` | 6.48 : 1           |

### D · Coffee — `coffee`

Dark, roasted, domestic. The cup inverted: roast is the ground, crema is the
text. Caramel and cherry are real tasting notes. Display: **Bricolage Grotesque**.

| Token  | Hex       | Contrast on ground |
| ------ | --------- | ------------------ |
| `bg`   | `#150F0A` | —                  |
| `surf` | `#221811` | 1.09 : 1           |
| `ink`  | `#F0E4D4` | 15.17 : 1          |
| `mut`  | `#A08C72` | 5.87 : 1           |
| `acc`  | `#D9903F` | 7.25 : 1           |
| `acc2` | `#D4705A` | 5.67 : 1           |

Ground and surface separate by only 1.09 : 1. Cards in this palette need a
stroke, not a fill, to read.

### E · Hacker Terminal — `terminal`

Dark, phosphor, grid. The two real CRT phosphors — P1 green and P3 amber — on
green-cast black, with a 1 px scanline every 4. Display: **IBM Plex Mono**,
the only monospace display in the set.

| Token  | Hex       | Contrast on ground |
| ------ | --------- | ------------------ |
| `bg`   | `#060A07` | —                  |
| `surf` | `#0C120D` | 1.05 : 1           |
| `ink`  | `#BFEFC8` | 15.55 : 1          |
| `mut`  | `#5F8A67` | 5.04 : 1           |
| `acc`  | `#3DDC7F` | 11.14 : 1          |
| `acc2` | `#F2A03D` | 9.36 : 1           |

Extra gradient layer:
`repeating-linear-gradient(180deg, rgba(61,220,127,.026) 0 1px, transparent 1px 4px)`

Phosphor green tires the eye in large blocks. Stroke, state and accent only —
never an area fill. With a monospace body face, drop the measure to ~60
characters.

### F · Blue Navy — `navy`

Dark, corporate, restrained. Boardroom navy with a warm counterweight; the
champagne is what stops it becoming generic. Display: **Archivo**.

| Token  | Hex       | Contrast on ground |
| ------ | --------- | ------------------ |
| `bg`   | `#0A1428` | —                  |
| `surf` | `#122040` | 1.14 : 1           |
| `ink`  | `#DCE4F2` | 14.36 : 1          |
| `mut`  | `#7E8FAE` | 5.62 : 1           |
| `acc`  | `#4D8EF0` | 5.63 : 1           |
| `acc2` | `#D9C39B` | 10.69 : 1          |

The champagne must appear in real states and real data, not as trim. If it only
decorates, this palette collapses into every other corporate template.

---

## 3. The dotted field

Two stacked layers behind the canvas, both `position: absolute; inset: 0`,
below content, `pointer-events: none`.

**Layer 1 — dots.** Soft-edged and semi-transparent. The long falloff is the
whole point: a hard 1 px circle aliases into a harsh mesh, a long ramp reads as
texture.

```css
--p-dot: radial-gradient(
  circle 2.2px at center,
  rgba(R, G, B, 0.12) 0%,
  rgba(R, G, B, 0.05) 46%,
  rgba(R, G, B, 0) 100%
);
```

Never return to a hard-stop dot.

| Palette   | Dot colour | Alpha      | Radius | Pitch |
| --------- | ---------- | ---------- | ------ | ----- |
| Nocturne  | `#D2D5E8`  | .12 → .05  | 2.2 px | 22 px |
| Overprint | `#2438C9`  | .15 → .06  | 2.0 px | 12 px |
| Tidepool  | `#DFAE54`  | .13 → .05  | 2.3 px | 27 px |
| Coffee    | `#D9903F`  | .13 → .05  | 2.4 px | 24 px |
| Terminal  | `#3DDC7F`  | .17 → .07  | 1.9 px | 18 px |
| Navy      | `#DCE4F2`  | .125 → .05 | 2.2 px | 23 px |

Each layer carries a `--p-dot-mask` so the grid fades toward the edges instead
of tiling to the frame. Overprint is the exception — printed matter does not
vignette, so its mask is flat.

**Layer 2 — gradient.** Two or three radial blooms plus a directional wash,
per palette, with `mix-blend-mode: var(--p-blend, normal)`.

---

## 4. Typography

| Role    | Face                                        | Use                                                 |
| ------- | ------------------------------------------- | --------------------------------------------------- |
| Display | `--p-display`, per palette                  | Headings, the empty-state greeting, wordmark        |
| Body    | System stack, or the palette's reading face | Message text, panel content                         |
| Utility | IBM Plex Mono                               | Labels, counts, hex values, timestamps, token names |

Measure stays near 65 characters for proportional faces, 60 for monospace.
Uppercase utility labels take `letter-spacing: .09em`. Headings take
`text-wrap: balance`. Digits that stack in a column take
`font-variant-numeric: tabular-nums`.

Only the active palette's display face loads. Do not ship six.

---

## 5. The composer — Orbit

A capsule floating over the canvas, with a **measured outline**: an outer ring
sitting 8 px clear of the capsule, dashed at rest, closing to 3 px and going
solid on focus. The outline is literally measured, and the motion says so.

| Part             | Spec                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Shape            | Capsule, `border-radius: 999px`, 54 px tall at rest                                                                          |
| Surface          | `color-mix(in oklab, var(--p-surf) 84%, transparent)` over `backdrop-filter: blur(14px)`                                     |
| Inner stroke     | `inset 0 0 0 1px var(--p-line)` plus `inset 0 1px 0 var(--p-hi)`                                                             |
| Outer ring       | `inset: -8px`, `1px dashed var(--p-line-2)`, opacity .55                                                                     |
| Ring on focus    | `inset: -3px`, solid, `var(--p-acc)`, opacity 1, 340 ms                                                                      |
| Mode orb         | 36 px, leading, off-centre highlight over `acc2 → acc`, with a `0 0 20px -6px` bloom in the accent; **is** the mode selector |
| Trailing cluster | Attach, dictate, then a split send: send plus a chevron for deeper modes                                                     |
| Send split       | `acc` → `acc2`-mixed gradient, `0 6px 18px -8px` accent glow, inner top highlight, lifts 1 px on hover                       |
| Cast shadow      | `0 18px 40px -24px` — the capsule floats; without it, it reads as painted on                                                 |
| Satellite chips  | Detached above the capsule — depth, pinned sources, web state                                                                |

Modes cycle Learn → Research → Explore. The orb is a button, not an ornament,
and carries an `aria-label` naming the current mode.

The composer carries **attach** and nothing else from the context toolbar. The two
are not duplicates and the split is worth keeping straight: the paperclip adds a
file _to the message you are writing_, the context toolbar's panel lists the files
_already in this thread_. Tools and MCP have no equivalent per-message action, so
they stay out of the composer entirely.

---

## 6. Icon buttons

Everything in the two toolbars is icon-driven. That raises the bar on labelling, not
lowers it.

| Property            | Value                                                                                                                 |
| ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Icon                | 20 px, `currentColor`, 1.6 stroke, round caps and joins                                                               |
| Target              | 44 × 44 px minimum, regardless of icon size                                                                           |
| Rest                | `color: var(--p-mut)`, transparent border                                                                             |
| Hover               | `color: var(--p-ink)`, `background: color-mix(in oklab, var(--p-ink) 8%, transparent)`, `border-color: var(--p-line)` |
| Active / panel open | `color: var(--p-acc)`, surface fill, accent hairline                                                                  |
| Focus               | `outline: 2px solid var(--p-acc); outline-offset: 2px`                                                                |
| Badge               | Top-right, tabular numerals, hidden at zero                                                                           |
| Label               | Translated `aria-label` **and** a translated tooltip. Both.                                                           |

Send is the one filled control: a gradient from `acc` toward `acc2`, with the
glyph in `--p-bg`. Overprint overrides the glyph to `#F4F3EF` because its ground
is light.

---

## 7. Scrollbars

Every scrollable surface in the app uses **OverlayScrollbars**, themed as
`os-theme-sofee`. Native scrollbars are never shown.

The handle is mixed from the active palette's ink, so it belongs to whichever of
the six palettes is on without a per-palette rule — and it is semi-transparent
throughout, because it sits over the dotted field and the gradient and an opaque
handle would punch a hole in both.

| Property       | Value                                                              |
| -------------- | ------------------------------------------------------------------ |
| Track          | 10 px, transparent at rest                                         |
| Handle         | 60% of the track at rest, 100% on hover; capsule radius            |
| Handle colour  | `--p-ink` at 20% / 32% hover / 44% active                          |
| Overprint      | Mixed from `--p-acc` instead — a printed palette has no grey glass |
| Minimum handle | 36 px                                                              |
| Hit area       | 3 px wider than the visible bar on each side                       |

**When it shows** is per surface, and it is a reading decision, not a style one:

| Surface                                     | `autoHide` | Why                                                               |
| ------------------------------------------- | ---------- | ----------------------------------------------------------------- |
| Message transcript                          | `scroll`   | At rest the reading surface stays clean                           |
| Dropdowns, panels, dialogs, command palette | `leave`    | A list you are browsing should advertise that there is more of it |

One integration constraint, and it is not negotiable: the scrolling element must
stay the element §3's ScrollController already owns. OverlayScrollbars is
initialised with the target declared as its own viewport and the padding and
content wrappers switched off, so no new scroll container is introduced. A
library that wraps the element would move the `scrollTop` that pinning, the
send-time hold and jump-to-latest all read and write.

---

## 8. Elevation

| Level | Use             | Treatment                              |
| ----- | --------------- | -------------------------------------- |
| 0     | Canvas          | The dotted field                       |
| 1     | Composer, cards | `--p-surf`, hairline, inner highlight  |
| 2     | Panels          | `--p-surf`, hairline, soft drop shadow |
| 3     | Menus, tooltips | `--p-surf-2`, hairline, tighter shadow |

Overprint replaces every blurred shadow with `--p-cast`, a hard 3 px offset.
One soft shadow breaks the printed illusion for the whole palette.

---

## 9. Spacing and radius

4 px base. Use 4, 8, 12, 16, 24, 32, 48, 64.

| Element                         | Radius |
| ------------------------------- | ------ |
| Capsule composer, chips, badges | 999 px |
| Panels, cards                   | 16 px  |
| Menus                           | 12 px  |
| Icon buttons                    | 10 px  |
| Swatches, inline markers        | 4 px   |

The toolbars float over the canvas at elevation 3, each on its own blurred
surface. The canvas reserves a 72 px gutter on each side for them and 78 px at the
top, always — including when the context toolbar is hidden. Canvas content caps at
760 px and centres.
