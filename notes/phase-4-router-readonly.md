# Phase 4 — Router Connectivity, Read Only

**Depends on:** P1 (Router model)
**Blocks:** P5
**Can start during P3** — mostly backend.

## Goal

Prove we can talk to real MikroTik hardware before we can break it. This phase reads. It
does not write. **No write call exists in the codebase when this phase ends.**

## Why read-only first

Every integration bug that would otherwise surface while modifying production config
surfaces here instead, where the worst outcome is a wrong number on a dashboard. By the
time P5 enables writes, connection handling, auth, timeouts, version differences, and
error mapping are all already proven against your actual routers.

---

## Tasks

### 4.1 Adapter skeleton

`librouteros 4.1.1` — pure Python, supports API-SSL on 8729. Wrap it; never import it
outside the adapter. Views and tasks talk to `RouterAdapter`, so a RADIUS backend can
implement the same interface later without touching anything above it.

```python
# apps/network/adapter.py

class RouterError(Exception): ...
class RouterUnreachable(RouterError): ...     # network/timeout
class RouterAuthFailed(RouterError): ...      # bad credentials
class RouterRejected(RouterError): ...        # RouterOS said no
class RouterUnsupported(RouterError): ...     # version lacks a capability


class RouterAdapter:
    def __init__(self, router: Router, *, dry_run: bool | None = None):
        self.router = router
        self.dry_run = router.dry_run if dry_run is None else dry_run
        self._api = None

    def __enter__(self):
        try:
            self._api = librouteros.connect(
                host=self.router.host,
                port=self.router.api_port,
                username=self.router.username,
                password=decrypt(self.router.password_enc),
                timeout=CONNECT_TIMEOUT,
                **(tls_kwargs() if self.router.use_tls else {}),
            )
        except librouteros.exceptions.TrapError as e:
            raise RouterAuthFailed(str(e)) from e
        except (socket.timeout, OSError) as e:
            raise RouterUnreachable(str(e)) from e
        return self

    def __exit__(self, *exc):
        if self._api:
            self._api.close()
```

- [ ] Timeouts on connect **and** on every call — a hung router must not hold a worker
- [ ] Credentials decrypted only inside the adapter, never held on the model instance
- [ ] Exceptions redact the password in `str()` and in any Sentry payload
- [ ] Connection reuse within one task; no pooling across tasks yet

### 4.2 Identity and capability discovery

- [ ] `identity()` → `/system/identity/print`
- [ ] `resource()` → `/system/resource/print` (version, board, CPU, uptime, free memory)
- [ ] Parse RouterOS version into a comparable tuple; store on the model
- [ ] Capability flags derived from version — v6 and v7 differ on some API paths, and the
      adapter should branch on a named capability, not a version check scattered through
      the code

### 4.3 Test connection action

- [ ] "Test connection" button on the router detail screen
- [ ] Runs synchronously via HTMX, returns within the timeout
- [ ] Distinguishes the three failure modes clearly in the UI:
      unreachable / auth failed / rejected — "connection failed" is not a useful message
- [ ] Updates `status`, `last_seen`, `routeros_version`, `board_name`
- [ ] Writes a `ServiceEvent`

### 4.4 Poller task

Celery beat, every ~30s for reachable routers, backing off for unreachable ones.

- [ ] `/ppp/active/print` — live PPPoE sessions: name, address, uptime, bytes in/out
- [ ] `/interface/print stats` — throughput per interface
- [ ] `/system/resource/print` — CPU, memory, uptime
- [ ] `/queue/simple/print stats` — per-queue counters for static-IP subscribers
- [ ] Store in a `RouterSnapshot` model, keeping a short rolling window (24–48h) rather
      than unbounded history
- [ ] Match active sessions to subscribers by `pppoe_username` / `static_ip`
- [ ] Exponential backoff on unreachable routers; do not hammer a dead device every 30s
- [ ] Per-router concurrency limit of 1 — never two pollers on the same device

### 4.5 Live UI

Fills the panels P3 left wired but empty.

- [ ] Dashboard router health table: state, session count, CPU bar, last seen
- [ ] Dashboard "online now" KPI from live session data
- [ ] Router detail: live stats, session list, subscriber count
- [ ] Subscriber detail: session IP, uptime, current throughput
- [ ] HTMX polling; stale data visibly marked as stale rather than silently shown as current

### 4.6 Import / match view

Before P5 can safely provision, we need to know what is already on each router.

- [ ] Read all `/ppp/secret` and `/queue/simple` entries from a router
- [ ] Match against subscribers by username / IP
- [ ] Three-column report: **matched**, **on router but not in DB**, **in DB but not on router**
- [ ] Read-only report — no adoption, no creation, no deletion in this phase
- [ ] This report is the input to the P5 rollout: it tells you exactly what the first
      reconciler run would encounter

---

## Testing

Real hardware is the point of this phase, but not for every test.

- [ ] Unit tests against a **fake adapter** returning recorded RouterOS responses
- [ ] Record real responses from a lab router as fixtures — RouterOS output shapes are
      quirky and hand-written fixtures will be wrong
- [ ] Integration test against a lab router (CHR in a VM is fine) in CI if feasible,
      manually otherwise
- [ ] Explicitly test: unreachable host, wrong password, wrong port, TLS mismatch,
      timeout mid-call, v6 vs v7 response differences

---

## Files touched

```
apps/network/adapter.py        new — the wrapper
apps/network/models.py         RouterSnapshot
apps/network/tasks.py          poller
apps/network/views.py          test connection, import report
apps/network/templates/        live panels
tests/fixtures/routeros/       recorded responses
requirements.txt               librouteros==4.1.1
```

## Exit criteria

- [ ] Dashboard shows live session counts from a **production** router
- [ ] Test-connection distinguishes all three failure modes correctly
- [ ] Poller survives a router going offline and recovers when it returns
- [ ] Import report generated for every production router
- [ ] **`grep -rn 'add\|set\|remove' apps/network/adapter.py` shows no write paths** —
      verify this deliberately before closing the phase
- [ ] Works against both RouterOS v6 and v7 if both exist in the fleet

## Risks

| Risk | Mitigation |
|------|------------|
| A write call sneaks in "just to test" | Explicit grep in exit criteria; adapter has no write methods defined at all in this phase |
| Poller saturates a CPU-limited router | Per-router concurrency of 1, 30s interval, backoff. Watch CPU on the smallest device in the fleet. |
| Credentials leak via exception/logging | Redaction tested explicitly; assert password string never appears in a formatted traceback |
| v6/v7 API differences discovered late | Capability flags from the start; test against both early |
| Session matching ambiguous | Report mismatches rather than guessing; this feeds the P5 rollout |

## Out of scope

Any write to a router (P5). Reconciliation or healing (P5). Adopting untracked router
objects (P5, and even there it needs human approval).
