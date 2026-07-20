# Phase 5 — Provisioning, Write Path

**Depends on:** P4
**Blocks:** P7
**First phase that writes to a router.**

## Goal

Create and modify router objects from Django, behind dry-run, with a reconciler that keeps
the two in sync without ever destroying config it does not own.

---

## The two rules that make this safe

### Rule 1 — We only ever touch what we own

Every object this system creates on a router carries an ownership marker in its `comment`
field. The reconciler will not modify or delete anything lacking that marker.

```python
COMMENT_PREFIX = "ispms"

def owned_tag(kind: str, pk: int) -> str:
    return f"{COMMENT_PREFIX}:{kind}:{pk}"      # ispms:sub:1042

def is_ours(row: dict) -> bool:
    return row.get("comment", "").startswith(COMMENT_PREFIX + ":")
```

**Why this matters more than it looks:** without ownership tags, the first reconciler run
on a production router deletes every PPPoE secret an engineer ever made by hand, because
none of them appear in the database. This single convention is the difference between a
safe reconciler and an outage.

### Rule 2 — Desired state, not commands

Nothing expresses "disable this user." It expresses "this subscriber's desired state is
suspended," and a worker makes the router match. Every operation is idempotent, so
replaying it is always safe — which is what lets us retry freely after a failure.

Hence every adapter write method is named `ensure_*`.

---

## Tasks

### 5.1 Packages become PPP profiles

The obvious approach puts a `rate-limit` on each individual PPPoE secret. **Don't.**
Mirror each package as a PPP profile on every router, and point secrets at the profile.

```
/ppp/profile/add
    name=ispms-home-10m
    rate-limit=2M/10M
    comment=ispms:pkg:7

/ppp/secret/add
    name=rahman.k
    password=<generated>
    service=pppoe
    profile=ispms-home-10m
    comment=ispms:sub:1042
```

The payoff: changing a package's speed is **one profile edit per router** instead of one
edit per subscriber. Repricing 800 subscribers on the 10 Mbps plan is a handful of API
calls, and there is no partial-failure state where some subscribers got the new speed and
others didn't.

- [ ] `ensure_profile(package)` — creates or updates the profile, tagged
- [ ] Profile sync runs on package save, across all enabled routers
- [ ] A new router gets all active package profiles on first provision

### 5.2 Rate limit construction

```python
def rate_limit(package) -> str:
    """RouterOS rate-limit is rx/tx FROM THE ROUTER'S POINT OF VIEW.
    rx = subscriber upload, tx = subscriber download.
    """
    return f"{package.upload_kbps}k/{package.download_kbps}k"
```

**This is a trap.** Getting the order backwards ships everyone a 10 Mbps upload and a
2 Mbps download, and it will be reported as "the internet is slow," not as a config bug.

- [ ] Built in exactly **one** function, used everywhere
- [ ] Unit test asserting the order explicitly
- [ ] Verified against real hardware before the phase closes — set a known package, connect
      a test client, run a speed test, confirm the direction

### 5.3 Subscriber provisioning

| Action | PPPoE | Static IP |
|--------|-------|-----------|
| Provision | `/ppp/secret/add` bound to package profile | `/queue/simple/add` target=`<ip>`, max-limit=up/down; optional `/ip/arp/add` |
| Change package | `/ppp/secret/set profile=` | `/queue/simple/set max-limit=` (instant, no reconnect) |
| Suspend | `/ppp/secret/set disabled=yes` **then** `/ppp/active/remove` | add IP to `ispms-suspended` address-list |
| Restore | `/ppp/secret/set disabled=no` | remove from address-list |
| Terminate | remove secret + active session | remove queue, ARP, address-list entry |

```python
class RouterAdapter:
    def ensure_profile(self, package) -> str: ...
    def ensure_pppoe_secret(self, sub) -> None: ...
    def ensure_queue(self, sub) -> None: ...
    def ensure_address_list(self, sub, listed: bool) -> None: ...
    def set_enabled(self, sub, enabled: bool) -> None: ...
    def kick_session(self, sub) -> bool: ...
    def remove_subscriber(self, sub) -> None: ...
    def list_owned(self, kind: str) -> list[dict]: ...
```

- [ ] All idempotent — running twice changes nothing the second time
- [ ] All tagged on create
- [ ] `provision_subscriber(pk)` task reads desired state and calls the right sequence
- [ ] Updates `sync_state` and `last_synced_at`; writes a `ServiceEvent` with the raw
      RouterOS response in `payload`

> **Disabling is not disconnecting.** Setting `disabled=yes` on a PPPoE secret stops the
> *next* authentication. An already-connected subscriber stays online, potentially for
> weeks, since PPPoE sessions do not re-auth on a timer. Suspension is only real when the
> active session is removed too. Both calls, always, in that order.

### 5.4 Static-IP suspension needs a firewall rule

The address-list approach only works if a rule actually drops that list.

- [ ] Document the required rule; it is infrastructure, not something we create per-subscriber:
      `/ip/firewall/filter add chain=forward src-address-list=ispms-suspended action=drop`
- [ ] Adapter **verifies the rule exists** on connect and refuses to suspend static-IP
      subscribers on a router where it is missing — silently adding an IP to a list nothing
      enforces means the subscriber stays online while the UI says suspended
- [ ] Consider a walled-garden redirect instead of a plain drop, so suspended customers see
      a "please pay your bill" page rather than a dead connection

### 5.5 Dry-run mode

- [ ] Default **on** for new routers (already the P1 model default)
- [ ] Adapter performs every read, logs writes instead of executing them
- [ ] Dry-run writes produce a readable diff: what exists, what would change
- [ ] Diff viewable per router and per subscriber in the UI
- [ ] Turning dry-run off is a permissioned action that writes a `ServiceEvent`

### 5.6 Job model and failure handling

- [ ] `ProvisioningJob` — subscriber, router, action, state, attempts, last error, timestamps
- [ ] Retry with exponential backoff on `RouterUnreachable`; **do not** retry
      `RouterRejected` (the router said no; retrying will not change its mind)
- [ ] Dead-letter view an operator can see and retry from
- [ ] Per-router rate limiting so bulk work cannot saturate a CPU-limited device and take
      a POP offline
- [ ] Jobs for the same subscriber serialize; never two workers provisioning one subscriber

### 5.7 Reconciler

Celery beat, every 15 minutes per router.

- [ ] Pull all owned objects: `/ppp/secret`, `/queue/simple`, `/ppp/profile`, address-lists
- [ ] Diff against desired state
- [ ] Apply the policy below
- [ ] Record drift count as a dashboard KPI; alert on sustained drift

| Drift | Risk | Action |
|-------|------|--------|
| Should be suspended, is active | Revenue loss | Heal immediately, automatic. Log. |
| Should be active, is suspended | **Customer harm** | Heal immediately, automatic. **Alert loudly** — a paying customer was offline. |
| Speed ≠ package | Moderate | Heal on next pass |
| Owned object on router, no subscriber in DB | Ambiguous | **Never auto-delete.** Flag for human review — this is what a bad migration looks like. |
| Untagged object | None | Ignore entirely. Not ours. |

### 5.8 Adoption of existing objects

The P4 import report listed what is already on each router. Adopting those is how existing
subscribers come under management.

- [ ] Explicit, human-approved action — never automatic
- [ ] Adopting means: match to a subscriber, add the ownership tag, set `sync_state`
- [ ] Show exactly what will change before confirming
- [ ] Reversible: un-adopting removes the tag and leaves the object untouched

---

## Rollout

1. Lab router only. Full test matrix.
2. One production router, dry-run on, for a week. Read the diff daily.
3. Same router, dry-run off, **new subscribers only**.
4. Adopt existing subscribers on that router, in batches.
5. Remaining routers, one at a time.

Do not skip step 2. The dry-run diff on a real router with real data is the only thing that
catches assumptions the lab did not.

---

## Files touched

```
apps/network/adapter.py        write methods added
apps/network/models.py         ProvisioningJob
apps/network/tasks.py          provision_subscriber, reconcile_router, sync_profiles
apps/network/reconcile.py      diff + policy
apps/network/views.py          dry-run diff, dead letters, adoption
apps/subscribers/services.py   transition() now actually provisions
```

## Exit criteria

- [ ] Subscriber created in Django appears correctly on a lab router, both connection types
- [ ] A hand-made, untagged secret survives a full reconciler pass untouched
- [ ] Rate-limit direction verified with a real speed test
- [ ] Package speed change propagates via profile edit, not per-subscriber writes
- [ ] Suspend drops the live session, verified by watching a connected client disconnect
- [ ] Static-IP suspend refuses to run on a router lacking the firewall rule
- [ ] Dry-run diff is accurate: what it predicted matches what happens when writes are on
- [ ] Failed jobs retry, then land in the dead-letter view

## Risks

| Risk | Mitigation |
|------|------------|
| **Reconciler destroys hand-built config** | Ownership tagging; never auto-delete; untagged ignored. Verified explicitly in exit criteria. |
| Rate limit inverted | One function, one test, one hardware verification |
| Bulk provisioning takes a POP offline | Per-router rate limiting; watch CPU during the first bulk run |
| Suspension appears to work but doesn't | Session kick is mandatory for PPPoE; firewall rule check is mandatory for static |
| Partial failure leaves inconsistent state | Idempotent `ensure_*` + retry + reconciler catches whatever the retry missed |

## Out of scope

Automatic expiry-driven suspension (P7). This phase provisions on demand only — a human or
a service-layer transition triggers everything.
