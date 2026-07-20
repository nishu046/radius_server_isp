# ISP Management Platform — Rebuild Plan

Working notes for taking this project from a CRUD record-keeping app to a system that
actively provisions and enforces internet service on MikroTik routers.

**Full PRD with diagrams and UI mockups:**
https://claude.ai/code/artifact/08635ccb-3c47-40f8-a389-01f2e80bb333

---

## Phases

Ordered by dependency. Each phase has its own note with tasks, code sketches, and exit criteria.

| # | Phase | Status | Depends on |
|---|-------|--------|------------|
| 0 | [Foundation & security](phase-0-foundation.md) | Not started | — |
| 1 | [Data model rework](phase-1-data-model.md) | Not started | P0 |
| 2 | [Design system & Tailwind setup](phase-2-design-system.md) | Not started | P0 |
| 3 | [Full UI redesign](phase-3-ui-redesign.md) | Not started | P1, P2 |
| 4 | [Router connectivity — read only](phase-4-router-readonly.md) | Not started | P1 |
| 5 | [Provisioning — write path](phase-5-provisioning.md) | Not started | P4 |
| 6 | [Billing & payments](phase-6-billing.md) | Not started | P1 |
| 7 | [Automatic enforcement](phase-7-enforcement.md) | Not started | P5, P6 |

### Why this order

The UI redesign is pulled forward ahead of all MikroTik work, but sits behind the data
model rework. The redesign rewrites every subscriber screen, and P1 changes the fields
those screens render — doing the redesign first means building them twice.

P2 (design system) only depends on P0, so it can run in parallel with P1 if there are
two people. P4 (read-only router access) can also start during P3, since it is mostly
backend.

Everything that can hurt a customer is deliberately late: P5 is the first phase that
writes to a router, and P7 is the first that can disconnect anyone.

---

## Baseline as of 2026-07-20

Already done — the app runs, but nothing below is production-ready.

- Django 6.0.7 on Python 3.14.3 (upgraded from a pinned Django 4.1 that could not
  install on this venv — see the memory note on the upgrade rationale)
- `django-crispy-forms` 2.6 + `crispy-bootstrap5` — **both removed in P3**
- SQLite — **replaced with PostgreSQL in P0**
- All migrations applied clean, no model drift
- Dev superuser `admin@example.com` — delete before any real deployment

## Known defects carried in from the existing codebase

Tracked here so they don't get lost; each is assigned to a phase.

| Defect | Impact | Fixed in |
|--------|--------|----------|
| `has_perm`/`has_module_perms` return `True` unconditionally | Any logged-in user is a full admin | P0 |
| No audit trail anywhere | Cannot answer "who disconnected this customer" | P0 |
| `UnorderedObjectListWarning` on every list view | Paginated rows silently duplicate or vanish | P0 |
| `apps/clients/Templates/`, `apps/onu/Templates/` capital-T | Breaks on case-sensitive Linux filesystems | P0 |
| `ALLOWED_HOSTS = ['*']` | Host header attacks | P0 |
| `Clients.ip` holds either an IP or a PPPoE username | Cannot provision anything | P1 |
| `Package.speed` is one integer | RouterOS needs separate up/down | P1 |

## Open decisions

These block P1 and P6. Listed in the PRD §13.

1. **PPPoE addressing** — router pool, or fixed address per secret?
2. **Grace period** — global, per-package, or per-subscriber? (modeled per-subscriber w/ global default)
3. **Billing anchor** — cycle from payment date, or fixed calendar day of month?
4. **Partial payments** — does a partial payment restore service?
5. **Router inventory** — how many, and RouterOS v6 or v7?

## Conventions

- **Router object ownership:** everything this system creates on a router carries
  `ispms:<kind>:<pk>` in its `comment` field. Nothing untagged is ever touched. See P5.
- **Service state is never written directly** — only through service-layer transitions
  that emit a `ServiceEvent`. See P1.
- **All router operations are `ensure_*`** and idempotent. See P5.
