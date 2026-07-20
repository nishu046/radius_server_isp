# Phase 2 — Design System & Tailwind Setup

**Depends on:** P0
**Blocks:** P3
**Can run in parallel with P1.**

## Goal

Get Tailwind building, define the tokens and component vocabulary, and convert exactly one
screen end to end as a proof. The full conversion is P3 — this phase is about making that
conversion mechanical rather than improvised.

## Why separate from P3

If the design system is invented while converting screens, the first five screens each get
a slightly different button. Pinning the vocabulary first means P3 is assembly, not design.

---

## Tasks

### 2.1 Tailwind build

Use the **standalone Tailwind CLI binary**, not the npm package — it avoids putting a Node
toolchain in the Django image.

- [ ] Download the standalone CLI, commit the version to the repo
- [ ] `static/src/input.css` → `static/dist/app.css`
- [ ] `tailwind.config.js` with `content` globs covering `templates/` and `apps/*/templates/`
- [ ] `make css` / `make css-watch` targets
- [ ] Production build minified, run in CI and in the Docker build
- [ ] Confirm `collectstatic` picks up `dist/app.css`

Note: P0 leaves `STATIC_ROOT` at `staticfiles/` and `STATICFILES_DIRS` at `static/` —
already fixed during the Django 6 upgrade, so the built CSS lands correctly.

### 2.2 Design tokens

Defined once as CSS custom properties, then referenced from `tailwind.config.js` so both
utility classes and hand-written CSS use the same values.

```js
// tailwind.config.js — theme.extend.colors
{
  ink:     { DEFAULT: '#10151C', 2: '#2C3742' },
  muted:   '#5C6773',
  line:    { DEFAULT: '#DCE1E8', 2: '#C3CBD5' },
  surface: { DEFAULT: '#FFFFFF', 2: '#EFF2F5' },
  canvas:  '#F6F7F9',

  brass:   { DEFAULT: '#8A6A2F', light: '#C9A063', bg: '#F3EDE1' },

  // semantic — service state ONLY, never used as a brand accent
  state: {
    active:    '#047857',
    grace:     '#B45309',
    suspended: '#BE123C',
    inactive:  '#5C6773',
  },
}
```

Rules that keep this coherent:

- **Brass is the only accent.** Primary buttons, focus rings, active nav, section marks.
- **Semantic colors are for service state only.** Never a button, never a heading.
- **Status is never carried by color alone.** Every state pill has a text label, so it
  works for colorblind users and on a phone in daylight.
- **Dark mode is token-level.** Redefine the custom properties under
  `@media (prefers-color-scheme: dark)` and `[data-theme]`; never style components inside
  a media query.

### 2.3 Typography

- [ ] System sans stack for interface text
- [ ] Monospace for **all network data** — IPs, PPPoE usernames, MACs, rate limits, router
      responses, account numbers. This is functional, not decorative: it signals "this is a
      value the router cares about, copy it exactly" and makes transposed digits visible.
- [ ] `tabular-nums` on every numeric column
- [ ] Type scale committed to the config; no arbitrary `text-[13px]` in templates

### 2.4 Component vocabulary

Build these as Django template partials in `templates/ui/`. P3 assembles from this set and
adds nothing new without a reason.

| Partial | Purpose |
|---------|---------|
| `ui/button.html` | `primary` / `secondary` / `danger`, with loading state |
| `ui/pill.html` | Service state, sync state, router state — label always rendered |
| `ui/field.html` | Label + input + help + error. **Replaces crispy-forms.** |
| `ui/table.html` | Wrapper enforcing `overflow-x-auto` so the page never scrolls sideways |
| `ui/kpi.html` | Dashboard stat tile — value, label, sub-detail, optional alert state |
| `ui/empty.html` | Empty state with a real next action, not just "no data" |
| `ui/modal.html` | Alpine-driven, focus-trapped |
| `ui/confirm.html` | Typed confirmation for destructive actions (see 2.6) |
| `ui/timeline.html` | Service history entries — used heavily on subscriber detail |

### 2.5 Form rendering without crispy

Crispy-forms goes away in P3, but the replacement is designed here.

```django
{# templates/ui/field.html #}
<div class="flex flex-col gap-1.5">
  <label for="{{ field.id_for_label }}"
         class="text-xs font-medium uppercase tracking-wide text-muted">
    {{ field.label }}{% if field.field.required %}<span class="text-state-suspended"> *</span>{% endif %}
  </label>
  {{ field }}
  {% if field.help_text %}<p class="text-xs text-muted">{{ field.help_text }}</p>{% endif %}
  {% for error in field.errors %}
    <p class="text-xs text-state-suspended">{{ error }}</p>
  {% endfor %}
</div>
```

- [ ] Widget base classes applied via a form mixin, so templates stay clean
- [ ] Error states styled at the field level, not just a summary block at the top
- [ ] `{% include %}`-based, so a form is a loop over fields

### 2.6 Interaction rules

Decided here, applied throughout P3.

- **HTMX** for anything that reflects server or router state: dashboard polling, in-flight
  provisioning jobs, inline row updates.
- **Alpine** for local UI state only: dropdowns, modals, the connection-type toggle that
  swaps PPPoE and static-IP fields.
- **Typed confirmation for destructive actions.** Suspending requires typing the
  subscriber's account number; a bulk action requires typing the affected count. An OK
  button is too easy to click through when the consequence is someone losing internet.
- **Never optimistic.** A row shows router-confirmed state or it shows `pending`. It never
  shows a state we merely hope is true. This rule matters more than it sounds — an
  optimistic UI on a provisioning system teaches operators to trust a screen that lies.
- **Visible focus states** on everything interactive.
- **`prefers-reduced-motion` respected.**

### 2.7 Proof screen

Convert **one** screen fully to validate the system before P3 scales it up.

- [ ] Pick the packages list — small, has a table, a form, and a destructive action
- [ ] Build it entirely from the partials above
- [ ] Light and dark both correct
- [ ] Works at 360px
- [ ] If anything needed a component not in 2.4, add it to the vocabulary before P3 starts

---

## Files touched

```
tailwind.config.js            new
static/src/input.css          new
static/dist/app.css           generated, gitignored
templates/ui/*.html           new — component vocabulary
templates/base.html           rewritten
apps/billing/templates/       proof screen
Makefile                      css targets
```

## Exit criteria

- [ ] `make css` produces a minified bundle; CI builds it
- [ ] Packages screen fully converted, using only vocabulary components
- [ ] Light and dark themes both verified, including the theme toggle overriding OS
      preference in both directions
- [ ] 360px viewport has no horizontal body scroll
- [ ] Keyboard navigation reaches every control with a visible focus ring
- [ ] Zero Bootstrap classes on the converted screen

## Risks

| Risk | Mitigation |
|------|------------|
| Design system grows ad hoc during P3 | The proof screen exists to surface missing components before P3, not after |
| Tailwind CDN used as a shortcut | Explicitly banned — CDN Tailwind has no purge, ships ~3MB, and blocks the CSP-safe path |
| Dark mode bolted on later | Tokens are defined for both themes in this phase; a component that only works in light mode is not done |

## Out of scope

Converting other screens (P3). Any new page that does not exist today.
