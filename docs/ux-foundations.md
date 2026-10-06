# UX Foundations

The reasoning behind how Sofee behaves. Read this before building a screen; it
settles the questions that every chat product gets wrong at least once.

Sofee is a **learning and research assistant**, not a coding agent. Sessions are
long, answers are long, and people read from the top rather than chase the
bottom. Almost every decision below follows from that one fact.

**Audience:** engineers building Sofee, and new teammates trying to understand
why it works the way it does.

---

## 1. Decisions on record

Where the shape of the product was settled, and by whom. The ones marked _house
call_ were made to unblock the build and are cheap to reverse; say so before the
components harden.

| Decision              | What it is                                                                | Why                                                                                                                          |
| --------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Header, not a sidebar | Four navigation icons in a horizontal cluster, floating top-left          | From the brief. Neither a sidebar nor a rail — the canvas runs the full width underneath it.                                 |
| Context cluster       | Four icons stacked vertically, floating top-right, **only inside a chat** | From the brief. Context management has nothing to say on an empty canvas.                                                    |
| Reserved gutters      | Both side gutters are held open even when the context cluster is hidden   | House call. Showing it on send must not move a pixel of the conversation, which is what §3.2's top-anchored hold depends on. |
| Composer              | Orbit (capsule)                                                           | House call. The context cluster owns attachments, tools and MCP; the Console variant's icon row would duplicate them.        |
| Default palette       | Nocturne                                                                  | House call. Safest first impression on day one. All six ship; this only sets the initial value.                              |

---

## 2. Layout

No sidebar and no rails. Two floating icon clusters over a single full-width canvas.

```
┌──────────────────────────────────────────────────────────┐
│ ┌──────────┐                                      ┌───┐  │
│ │ ＋ ▤ ⬓ ⋮ │   header, floating, pushed left       │ ⚒ │  │
│ └──────────┘                                      │ ⬡ │  │
│                                                   │ 📎│  │
│                     conversation                  │ ⋮ │  │
│                                                   └───┘  │
│                                                   ┌───┐  │
│                                                   │ ▓ │  │
│                ╭──────────────────╮               └───┘  │
│                │     composer     │            context,  │
│                ╰──────────────────╯       chat only      │
└──────────────────────────────────────────────────────────┘
```

Both clusters are absolutely positioned above the canvas rather than columns in
the layout, and the canvas reserves a gutter on each side so conversation text
never runs under them. The gutters are reserved **unconditionally**, including
on the home canvas where the context cluster is absent — showing it on send must
not move a single pixel of the conversation, which is what §3.2's top-anchored
hold depends on.

### 2.1 Header — navigation

Four buttons, left to right, in this order:

| Button       | Opens             | Notes                                           |
| ------------ | ----------------- | ----------------------------------------------- |
| **New**      | Dropdown menu     | See §2.3                                        |
| **Chats**    | Anchored dropdown | Conversation history                            |
| **Projects** | Anchored dropdown | Project list                                    |
| **More**     | Dropdown menu     | Settings, language, palette, keyboard shortcuts |

### 2.2 Context cluster

Visible only inside a chat, never on the home canvas. Four buttons stacked top to
bottom, plus a context meter on its own surface directly below them:

| Button          | Opens               | Badge                          |
| --------------- | ------------------- | ------------------------------ |
| **Tool calls**  | Right overlay panel | Count of calls in this thread  |
| **MCP**         | Right overlay panel | Count of connected servers     |
| **Attachments** | Right overlay panel | Count of files in this thread  |
| **More**        | Dropdown menu       | Compact context, Clear context |

The **context meter** is a thin vertical fill below the context cluster showing
how much of the window is consumed. It is not decoration: Compact and
Clear act on exactly what it measures, so the control and its readout sit
together. It changes colour at 75% (warning) and 90% (critical) using semantic
tokens, never the palette accent.

### 2.3 The New menu

Opens below the button. Three items, in this order:

1. **New chat** — default action; also bound to the primary shortcut
2. **New project**
3. **New temporary chat**

A temporary chat is never written to history. It must be visually unmistakable,
because the cost of confusing it with a normal chat is losing work:

- A persistent badge in the canvas header reading _Temporary_
- A dashed treatment on the composer's outer ring rather than solid
- On close or navigate-away, a confirmation that names what will be lost

### 2.4 Overlays never push

Two shapes, chosen by what the content is:

| Trigger                               | Shape                                   | Size                                      |
| ------------------------------------- | --------------------------------------- | ----------------------------------------- |
| Header: Chats, Projects               | **Anchored dropdown**, under the button | 400 px wide, capped at `min(56vh, 520px)` |
| Context: tool calls, MCP, attachments | **Centred card**, pushed right          | 360 px wide, height by content            |

A list of recent chats is something you glance at and dismiss. Giving it a
floor-to-ceiling sheet makes it read as a mode you have entered rather than a
menu you have opened, so the header's two list buttons open a bounded dropdown
instead — big enough for a real page of titles, small enough that the canvas
stays visible around it. The context overlays are not capped — their content is
inspected rather than picked from, so they take the height they need — but they sit
centred against the right edge rather than stretched floor to ceiling.

Neither shape resizes the conversation column.

This is the load-bearing decision of the whole layout. Pushing the canvas
reflows the message list, which invalidates every cached message height and
throws away scroll position — the single most disorienting thing a chat app can
do while someone is mid-paragraph. Overlays preserve reading context completely.

Rules:

Both share one dismissal contract:

- One overlay open at a time. Opening a second closes the first.
- `Esc` closes. Click outside closes. The trigger button reflects open state.
- Focus moves in on open and returns to the trigger on close.
- On a narrow window both become bottom sheets — the dropdown at 60vh, the context card at 80vh.

---

## 3. Scroll behaviour

The hardest part of any chat UI, and the part users notice only when it is
wrong. Four failure modes to design against:

1. Being yanked to the bottom while reading something above
2. Sub-pixel jitter as streamed tokens land
3. The browser's scroll anchoring fighting our own scroll management
4. Late-loading content (images, code blocks, math) shifting text under the cursor

### 3.1 The pin state machine

The message list is either **pinned** to the bottom or **free**.

```
                 user scrolls up > 48px
        ┌──────────────────────────────────┐
        │                                  ▼
   ╔════════╗                          ╔══════╗
   ║ pinned ║                          ║ free ║
   ╚════════╝                          ╚══════╝
        ▲                                  │
        └──────────────────────────────────┘
       returns within 48px of bottom, or
       sends a message, or taps Jump to latest
```

Start **pinned**. While pinned, new content keeps the bottom edge in view.
While free, nothing scrolls on its own — ever.

**Detect intent, not position.** Do not infer "the user scrolled" from a
`scroll` event, because programmatic scrolls fire it too and the resulting race
is the source of most autoscroll bugs. Listen for `wheel`, `touchmove`, and
scroll-relevant `keydown` instead. Those only come from a person.

```ts
// Intent-driven, not position-driven.
const UNPIN_THRESHOLD_PX = 48;

function distanceFromBottom(el: HTMLElement): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

function onUserScrollIntent(el: HTMLElement): void {
  pinned = distanceFromBottom(el) <= UNPIN_THRESHOLD_PX;
}
```

### 3.2 Reading position on send

When the user sends a message, do **not** scroll to the bottom of the thread.
Scroll so their message sits at the **top** of the viewport, and let the reply
stream downward into the empty space below it.

For a research tool this is the single highest-value scroll decision. Answers
run long. Bottom-anchored streaming makes people read the tail of a paragraph
while its beginning scrolls away above them. Top-anchored streaming means they
read from the first word, at rest, and the text comes to them.

This requires a spacer below the last message tall enough that the user's
message can actually reach the top:

```css
.thread-tail {
  min-block-size: calc(100dvh - var(--composer-block-size));
}
```

The spacer collapses once the reply is long enough to fill it.

### 3.3 While streaming

- Observe content growth with a `ResizeObserver` on the message list, not with
  token events. One observer callback per frame beats one scroll per token.
- When pinned, set `scrollTop = scrollHeight` directly. Never `scrollIntoView`
  with `behavior: "smooth"` during streaming — smooth scrolls queue and fight
  each other.
- Set `overflow-anchor: none` on the list. Browser scroll anchoring and manual
  pinning both try to own the same value; let ours win.
- Reserve space for the thinking indicator so the first token does not shift
  layout. The indicator and the first line of the reply occupy the same height.
- Pause autoscroll while `document.visibilityState === "hidden"`; catch up once
  on `visibilitychange`.

### 3.4 Jump to latest

While free, a floating control appears above the composer: **Jump to latest**,
with a count when messages arrived while the user was away from the bottom. It
smooth-scrolls (unless reduced motion) and re-pins.

It appears only when free and the distance from bottom exceeds one viewport
height — showing it 60 px from the bottom is noise.

### 3.5 Per-thread scroll memory

Switching conversations restores the previous scroll offset for that thread,
keyed by thread id. Returning to a conversation you were reading and landing
back at the bottom is a small betrayal. Store offset plus the id of the topmost
visible message; restore by message id when heights have changed.

---

## 4. Conversation dynamics

### 4.1 Sending

1. The user message renders **immediately**, optimistically, before any server
   acknowledgement, in a pending state.
2. The composer clears and keeps focus.
3. Scroll positions the new message at the top (§3.2).
4. Send becomes Stop **in the same slot** — no layout shift, no button moving
   under a cursor that is about to click.

If the send fails, the message stays in place with an inline error and a Retry
action. It is never removed, and the error is never a toast. Toasts vanish;
this needs to persist until resolved.

### 4.2 Streaming cadence

Tokens arrive in bursts. Rendering each one as it lands produces visible
stutter. Buffer to one animation frame and flush.

Do not animate individual characters. A typewriter effect on top of real
streaming is two clocks fighting, and it slows reading down for no gain.

### 4.3 States that need real design

Every one of these is a screen someone will see on their first day:

| State           | Requirement                                                                                           |
| --------------- | ----------------------------------------------------------------------------------------------------- |
| Empty thread    | The canvas is the hero: greeting, three concrete starting moves, composer. No empty-box illustration. |
| Thinking        | Stable height, indefinite (no fake progress bar), cancellable                                         |
| Streaming       | Stop available at all times                                                                           |
| Stopped by user | Partial reply is kept, clearly marked as incomplete, with Continue                                    |
| Error           | Inline, in the thread, states what failed and what to do, with Retry                                  |
| Offline         | Composer stays usable; the message queues and sends on reconnect                                      |
| Empty chat list | Explains what will appear here, with a New chat action                                                |

### 4.4 Message affordances

Controls appear on hover **and** on keyboard focus. Hover-only controls do not
exist for keyboard users.

- **User messages:** Copy, Edit and resend
- **Assistant messages:** Copy, Regenerate, Good/Bad feedback
- Editing a user message forks the thread rather than destroying what followed;
  the previous branch stays reachable.

### 4.5 Citations

A research assistant that cannot show its sources is a rumour mill. Inline
superscript references link to a source list at the end of the message. Hovering
or focusing a reference previews the source. Clicking opens it in the
Attachments panel when it is a local document, or a new tab when it is a URL.

---

## 5. The composer

The Orbit capsule (see the design system document).

| Behaviour | Rule                                                                                                                    |
| --------- | ----------------------------------------------------------------------------------------------------------------------- |
| Submit    | `Enter` sends, `Shift+Enter` inserts a newline. Configurable to the inverse.                                            |
| IME       | Never send while `event.isComposing` is true. Japanese, Chinese and Korean input all use `Enter` to commit a candidate. |
| Growth    | Auto-grows to a maximum, then scrolls internally. Never grows past 40% of the viewport.                                 |
| Drafts    | Persisted per thread; switching away and back restores the text.                                                        |
| Paste     | Files and images attach. Text over ~2 000 characters offers to attach as a document instead of flooding the input.      |
| Drop      | Dropping a file anywhere on the canvas attaches it; the whole canvas is the drop target, with a visible state.          |
| Empty     | Submit is disabled and visibly so when the input is empty and nothing is attached.                                      |
| Focus     | The composer holds focus on load and after every send.                                                                  |

---

## 6. Keyboard

A research tool is used for hours. Keyboard access is not an accessibility
checkbox here; it is the primary interface for anyone who stays.

| Keys                     | Action                                             |
| ------------------------ | -------------------------------------------------- |
| `Ctrl/Cmd + K`           | Command palette                                    |
| `Ctrl/Cmd + N`           | New chat                                           |
| `Ctrl/Cmd + Shift + N`   | New temporary chat                                 |
| `Ctrl/Cmd + J`           | Toggle the Chats panel                             |
| `Ctrl/Cmd + /`           | Keyboard shortcuts                                 |
| `Esc`                    | Close panel or menu; if none open, stop generation |
| `↑` in an empty composer | Edit the last user message                         |
| `Alt + ↑ / ↓`            | Move between messages                              |

Both clusters are `role="toolbar"` with roving `tabindex`: one tab stop each,
arrow keys move within them along their own axis.

---

## 7. Internationalisation

English and Spanish at launch. The architecture must not assume two.

### 7.1 Rules

- **No user-facing literal strings in components.** Enforced by lint.
- **No concatenation.** Full sentences with named placeholders. Word order is
  not universal, and a sentence assembled from fragments cannot be translated
  well in either direction.
- **Plurals through `Intl.PluralRules`**, never `count === 1 ? … : …`.
- **Dates, numbers, relative times through `Intl`** — `DateTimeFormat`,
  `NumberFormat`, `RelativeTimeFormat`. Never hand-rolled.
- **Locale resolution order:** stored preference → `navigator.languages` → `en`.
- `<html lang>` tracks the active locale. Screen readers switch voice on it.
- Locale bundles load lazily; only the active locale ships in the initial chunk.

### 7.2 Designing for Spanish

Spanish runs roughly 20–30% longer than English. This is a layout constraint,
not a translation problem:

- No fixed-width buttons or labels
- Test every screen in `es` before calling it done
- Truncate only where unavoidable, always with the full text available on
  hover and focus
- Icon-only toolbar buttons carry `aria-label` and a tooltip, both translated

### 7.3 Terminology

Fixed translations for the concepts that repeat. Agree them once; do not let
each screen invent its own.

| English         | Español               |
| --------------- | --------------------- |
| Chat            | Chat                  |
| Temporary chat  | Chat temporal         |
| Project         | Proyecto              |
| Tool call       | Llamada a herramienta |
| Attachment      | Adjunto               |
| Compact context | Compactar contexto    |
| Clear context   | Limpiar contexto      |
| Jump to latest  | Ir a lo último        |
| Regenerate      | Volver a generar      |
| Stop            | Detener               |

---

## 8. Accessibility

| Area      | Requirement                                                                                                                                                                                                                  |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Contrast  | Verified in all six palettes; body text ≥ 4.5:1, large text and UI ≥ 3:1                                                                                                                                                     |
| Focus     | Always visible, never removed, 2 px offset ring from the palette accent                                                                                                                                                      |
| Toolbars  | `role="toolbar"`, roving tabindex, translated `aria-label` per button                                                                                                                                                        |
| Panels    | `role="dialog"`, `aria-modal`, focus trapped, focus returned on close                                                                                                                                                        |
| Menus     | `role="menu"` / `menuitem`, arrow keys, `Home`/`End`, typeahead, `Esc`                                                                                                                                                       |
| Messages  | `role="article"` with an accessible name identifying the speaker                                                                                                                                                             |
| Streaming | Announce _Response started_ and _Response complete_ through a polite live region. **Never** put the streaming text itself in a live region — it re-announces on every token and makes the app unusable with a screen reader. |
| Targets   | 44 × 44 px minimum for every toolbar and composer control                                                                                                                                                                    |
| Skip link | First tab stop jumps to the composer                                                                                                                                                                                         |

---

## 9. Motion

Motion clarifies where things came from. It is not decoration, and there is
very little of it.

| Element             | Duration | Easing                      |
| ------------------- | -------- | --------------------------- |
| Panel slide + fade  | 200 ms   | `cubic-bezier(.2,.8,.25,1)` |
| Scrollbar fade      | 120 ms   | `ease-out`                  |
| Dropdown menu       | 120 ms   | `ease-out`                  |
| Composer focus ring | 340 ms   | `cubic-bezier(.2,.8,.25,1)` |
| Jump to latest      | 160 ms   | `ease-out`                  |

**Message append is never animated.** A fade or slide on arriving content
fights the scroll controller and produces the jitter §3 exists to prevent.

Under `prefers-reduced-motion: reduce`: transforms become opacity crossfades,
smooth scrolls become instant, the composer ring changes colour without
travelling.

---

## 10. Performance budgets

| Metric                 | Budget                       | Why it is this number                                                |
| ---------------------- | ---------------------------- | -------------------------------------------------------------------- |
| First contentful paint | < 1.2 s on a mid-tier laptop | Day-one impression                                                   |
| Composer interactive   | < 300 ms after paint         | It holds focus on load; it must accept typing immediately            |
| Streaming frame budget | 16 ms                        | Anything slower is visible stutter during the thing users watch most |
| Thread of 500 messages | Scrolls at 60 fps            | Virtualise above 100 messages, preserving scroll anchoring           |
| Initial JS             | < 120 KB gzipped             | Only the active locale ships                                         |

---

## 11. What this document does not cover

The visual system — palettes, token names, the dotted field, the composer's
measured outline, typography — lives in `design-system.md`. Where the two
documents disagree, this one wins on behaviour and that one wins on appearance.
