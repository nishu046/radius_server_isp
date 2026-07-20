# Phase 7 — Automatic Enforcement

**Depends on:** P5 (provisioning), P6 (billing)
**Blocks:** nothing
**This is the phase that can cause an outage.**

## Goal

Close the loop: when a subscription lapses, service stops automatically. When a payment
lands, service resumes automatically.

Everything before this was reversible by a human noticing. This phase acts on thousands of
customers without anyone watching, which is why it is last and why more than half of it is
safety machinery.

---

## The expiry sweep

Celery beat, every 15 minutes.

```python
@shared_task
def sweep_expiries():
    now = timezone.now()

    # active -> grace
    with transaction.atomic():
        rows = (Subscriber.objects
                .select_for_update(skip_locked=True)
                .filter(service_state='active',
                        expires_at__isnull=False,      # NULL never expires
                        expires_at__lt=now))
        for sub in rows:
            transition(sub, 'grace', reason='expired', actor=None)

    # grace -> suspended
    candidates = (Subscriber.objects
                  .filter(service_state='grace',
                          expires_at__isnull=False)
                  .annotate(cutoff=F('expires_at') + F('grace_days') * timedelta(days=1))
                  .filter(cutoff__lt=now))

    if breaker_trips(candidates.count()):
        raise_for_approval(candidates)      # stops here; suspends nothing
        return

    with transaction.atomic():
        for sub in candidates.select_for_update(skip_locked=True):
            transition(sub, 'suspended', reason='grace_elapsed', actor=None)
            provision_subscriber.delay(sub.pk)     # router work off the sweep
```

Key details:

- **`expires_at__isnull=False`** — P1 leaves migrated subscribers with `NULL` expiry
  because there is no source data. A `NULL` must never expire, or the first sweep suspends
  your entire existing customer base.
- **`select_for_update(skip_locked=True)`** — overlapping sweeps cannot double-process a
  subscriber. Requires PostgreSQL (P0).
- **Router work is enqueued, never inline.** A slow or dead router must not stall the sweep.
- Grace transitions do not provision — a subscriber in grace is still online. Only the
  suspend transition touches the router.

---

## Tasks

### 7.1 Circuit breaker

The single most important thing in this phase.

- [ ] Threshold: a sweep that would suspend more than **5% of active subscribers or 25
      accounts, whichever is lower**, stops and asks
- [ ] Writes a pending batch record, alerts an owner, **suspends nothing**
- [ ] Approval UI showing exactly who would be cut and why
- [ ] Approval is permissioned (`owner` only) and logged
- [ ] Batch expires if unapproved — stale batches must not execute a day later against
      changed data

A clock skew, a botched migration, a timezone conversion bug, or a bad `billing_cycle_days`
value is far more likely to produce "3,000 subscribers expired simultaneously" than reality
is. The breaker turns a company-ending Saturday into a notification.

### 7.2 Grace handling

- [ ] `grace` state is fully online — warned, not cut
- [ ] Dashboard KPI: how many in grace, how many cut in the next 24h
- [ ] Grace period per subscriber with a global default (P1 model)
- [ ] Notification hook left as an extension point — SMS is out of scope, but the
      transition should call something so it can be wired later

### 7.3 Suspension path

- [ ] PPPoE: `disabled=yes` **then** `/ppp/active/remove`. Both, always, in that order.
- [ ] Static IP: add to `ispms-suspended` address-list, after verifying the firewall rule
      exists (P5)
- [ ] Failure to kick the session marks `sync_state='failed'`, not `synced` — a subscriber
      whose secret is disabled but whose session is live is **not** suspended
- [ ] Every suspension writes a `ServiceEvent` with the router response

### 7.4 Reconnection — the fast path

A collector standing at a customer's door needs this to feel instant.

- [ ] Payment → extend expiry → transition to `active` → enqueue on the **priority queue**
- [ ] Priority queue jumps ahead of bulk reconciliation work
- [ ] UI polls the job via HTMX and shows "Reconnected" only on router confirmation
- [ ] Target: under 10 seconds from payment confirmation to service restored
- [ ] If the router is unreachable, say so plainly — "payment recorded, reconnection
      pending, router unreachable" beats a spinner or a false success

### 7.5 Manual override

- [ ] Manager can suspend or restore outside the automatic flow
- [ ] Requires a reason, recorded in `ServiceEvent`
- [ ] Typed confirmation (P2) — type the account number
- [ ] An overridden subscriber is flagged so the next sweep does not immediately undo the
      override. Decide the semantics explicitly: a manual restore without payment should
      set a short expiry extension rather than a flag the sweep ignores forever.

### 7.6 Shadow mode

The gate before this phase is allowed to touch anyone.

- [ ] Sweep runs on schedule, computes every transition, writes what it *would* do
- [ ] Executes nothing
- [ ] Daily report comparing predicted suspensions against what staff actually did manually
- [ ] Run for a **full week** minimum
- [ ] Any mismatch is investigated before enablement, not explained away

### 7.7 Staged rollout

1. **Shadow mode, whole fleet, one week.** Predictions must match reality.
2. **One POP, live.** Smallest one. Watch for a full billing cycle.
3. **Remaining POPs**, one at a time, a few days apart.
4. Circuit breaker stays on permanently — it is not a rollout tool.

- [ ] Enablement is per-router or per-POP, not global
- [ ] Kill switch: a single setting that halts all automatic suspension immediately,
      reachable without a deploy

### 7.8 Monitoring

- [ ] Dashboard: suspensions today, restorations today, sweep last-run time
- [ ] Alert if the sweep has not run in 30 minutes — a silently dead beat means non-payers
      stay online indefinitely
- [ ] Alert on any `should be active, is suspended` drift (P5 reconciler) — that is a
      paying customer offline
- [ ] Alert when the breaker trips
- [ ] Weekly: suspensions that were reversed within 24h, which usually means a billing bug

---

## Files touched

```
apps/subscribers/tasks.py     sweep_expiries
apps/subscribers/breaker.py   circuit breaker + approval batches
apps/subscribers/services.py  override paths
apps/network/tasks.py         priority reconnect queue
apps/billing/services.py      payment triggers priority provisioning
templates/                    approval UI, kill switch, monitoring panels
```

## Exit criteria

- [ ] **A full week in shadow mode where predicted suspensions exactly match what staff
      would have done manually.** Not "close" — exactly, with every difference explained.
- [ ] Circuit breaker verified by a deliberate test: set a bad expiry on many test
      subscribers, confirm the sweep stops and asks
- [ ] `NULL` expiry never suspends, asserted by test
- [ ] Suspension verified end to end: a connected test client actually loses connectivity
- [ ] Reconnection after payment under 10 seconds on a healthy router
- [ ] Kill switch halts suspension without a deploy
- [ ] Sweep-not-running alert fires when beat is stopped

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Mass wrongful disconnection** | Critical | Circuit breaker with owner approval; shadow week; staged rollout; kill switch |
| Clock skew or timezone bug expires everyone | Critical | NTP on all hosts; store UTC; Asia/Dhaka conversion only at edges; breaker catches the blast |
| `NULL` expiry treated as expired | Critical | Explicit filter + test. This is the single most likely way to cut off every migrated customer. |
| Beat dies silently, non-payers stay online | High | Last-run alert at 30 minutes |
| Suspension appears successful but session persists | High | Kick is mandatory; failure marks `failed`, not `synced` |
| Paying customer suspended by a billing bug | High | Reconciler alerts on wrong-direction drift; 24h-reversal report catches patterns |
| Override fights the sweep | Moderate | Explicit override semantics decided in 7.5, tested both directions |

---

## After this phase

The loop is closed. Natural follow-ons, none of which are committed:

- SMS notification before grace expiry (the hook exists from 7.2)
- Subscriber self-service portal — check balance, pay, view usage
- Online payment gateway, which would make reconnection fully hands-off
- Usage-based or FUP packages, which need accounting data the poller already collects
- If the fleet grows past what direct API comfortably handles, a RADIUS backend
  implementing the same `RouterAdapter` interface — the reason that interface exists
