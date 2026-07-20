# Phase 1 — Data Model Rework

**Depends on:** P0 (Postgres, audit log)
**Blocks:** P3 (redesign renders these fields), P4, P6
**Ships no visible features.**

## Goal

Reshape the schema so provisioning and billing have something to stand on. No router code
in this phase — the point is to get the shape right while it is still cheap to change.

## Open decisions that block this phase

1. **PPPoE addressing** — pool on the router, or fixed address per secret? If fixed, we
   need an `IPPool` model and allocation logic.
2. **Grace period** — modeled below as per-subscriber with a global default. Confirm.
3. **Billing anchor** — affects `Subscription.period_start` semantics in P6, but the field
   shape is the same either way, so P1 is not truly blocked.

---

## Tasks

### 1.1 New apps

- [ ] `apps.subscribers` — replaces `apps.clients`
- [ ] `apps.billing` — packages move here from `apps.packages`
- [ ] `apps.network` — already created in P0 for `ServiceEvent`; gains `Router` here

Keep `apps.packages` as a thin shim during migration, or move `Package` and update imports
in one commit. Prefer the latter — the shim will outlive its usefulness.

### 1.2 Router model

```python
class Router(models.Model):
    class Status(models.TextChoices):
        UNKNOWN     = 'unknown'
        REACHABLE   = 'reachable'
        UNREACHABLE = 'unreachable'
        AUTH_FAILED = 'auth_failed'

    name        = models.CharField(max_length=100, unique=True)
    pop         = models.ForeignKey('pop.Pop', null=True, on_delete=models.SET_NULL)

    host        = models.GenericIPAddressField()
    api_port    = models.PositiveIntegerField(default=8728)   # 8729 = API-SSL
    use_tls     = models.BooleanField(default=False)
    username    = models.CharField(max_length=100)
    password_enc = models.BinaryField()                        # Fernet

    # discovered on connect
    routeros_version = models.CharField(max_length=30, blank=True)
    board_name       = models.CharField(max_length=60, blank=True)

    status      = models.CharField(max_length=20, choices=Status, default=Status.UNKNOWN)
    last_seen   = models.DateTimeField(null=True, blank=True)

    # safety
    dry_run     = models.BooleanField(default=True)   # ON by default for new routers
    enabled     = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
```

- [ ] Fernet helper for `password_enc` — key from `ROUTER_CRED_KEY` env var, never in DB
- [ ] Password is write-only in forms and admin; never rendered back, never logged
- [ ] `dry_run` defaults **True** so a newly added router cannot be written to by accident

### 1.3 Package rework

Current model is `name`, `speed` (one int), `price`.

```python
class Package(models.Model):
    name           = models.CharField(max_length=100, unique=True)

    download_kbps  = models.PositiveIntegerField()
    upload_kbps    = models.PositiveIntegerField()
    burst_download_kbps = models.PositiveIntegerField(null=True, blank=True)
    burst_upload_kbps   = models.PositiveIntegerField(null=True, blank=True)

    price              = models.DecimalField(max_digits=10, decimal_places=2)
    billing_cycle_days = models.PositiveIntegerField(default=30)

    is_active      = models.BooleanField(default=True)

    class Meta:
        ordering = ['download_kbps', 'name']

    @property
    def profile_name(self) -> str:
        """Name of the mirrored PPP profile on each router. Used in P5."""
        return f"ispms-{slugify(self.name)}"
```

- [ ] Migration: `speed` → `download_kbps`; set `upload_kbps` to a sensible default and
      **flag every row for review** — the old single value cannot tell us the upload rate
- [ ] `price` becomes `Decimal`, not `Float`. Money is never a float.
- [ ] Note: `Commission.profit` and the `Invest`/`Earning` amounts are also
      `Float`/`Integer` — convert to `Decimal` in the same migration

### 1.4 Subscriber — the central rework

Replaces `apps.clients.models.Clients`.

```python
class Subscriber(models.Model):
    class Connection(models.TextChoices):
        PPPOE     = 'pppoe'
        STATIC_IP = 'static_ip'

    class State(models.TextChoices):
        PENDING    = 'pending'
        ACTIVE     = 'active'
        GRACE      = 'grace'
        SUSPENDED  = 'suspended'
        TERMINATED = 'terminated'

    class Sync(models.TextChoices):
        SYNCED  = 'synced'
        PENDING = 'pending'
        DRIFTED = 'drifted'
        FAILED  = 'failed'

    # identity
    account_no = models.CharField(max_length=30, unique=True)   # was client_id
    name       = models.CharField(max_length=150)
    email      = models.EmailField(blank=True)
    phone      = models.CharField(max_length=30)
    nid        = models.CharField(max_length=50, blank=True)
    address    = models.CharField(max_length=255)

    # connection
    connection_type = models.CharField(max_length=20, choices=Connection)
    pppoe_username  = models.CharField(max_length=64, unique=True, null=True, blank=True)
    pppoe_password_enc = models.BinaryField(null=True)
    static_ip       = models.GenericIPAddressField(protocol='IPv4', unique=True,
                                                   null=True, blank=True)
    mac_address     = models.CharField(max_length=17, blank=True)

    # service
    router  = models.ForeignKey('network.Router', on_delete=models.PROTECT)
    package = models.ForeignKey('billing.Package', on_delete=models.PROTECT)
    onu     = models.ForeignKey('onu.Onu', null=True, blank=True, on_delete=models.SET_NULL)
    pop     = models.ForeignKey('pop.Pop', null=True, blank=True, on_delete=models.SET_NULL)

    service_state = models.CharField(max_length=20, choices=State, default=State.PENDING)
    expires_at    = models.DateTimeField(null=True, blank=True, db_index=True)
    grace_days    = models.PositiveIntegerField(default=3)
    auto_renew    = models.BooleanField(default=True)

    sync_state    = models.CharField(max_length=20, choices=Sync, default=Sync.PENDING)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created', '-id']
        constraints = [
            models.CheckConstraint(
                name='pppoe_requires_username',
                condition=~Q(connection_type='pppoe') | Q(pppoe_username__isnull=False),
            ),
            models.CheckConstraint(
                name='static_requires_ip',
                condition=~Q(connection_type='static_ip') | Q(static_ip__isnull=False),
            ),
        ]
```

Notes on specific choices:

- `expires_at` is indexed — the P7 sweep queries it every 15 minutes.
- `router` and `package` use `PROTECT`, not `CASCADE`. The current models use `CASCADE`
  everywhere, which means **deleting a package deletes its subscribers**. That is a
  data-loss bug waiting to happen.
- `onu` and `pop` become `SET_NULL` — a damaged ONU should not delete the customer.
- `pppoe_password` is encrypted, not hashed. Support staff need to read it back to a
  customer over the phone.
- `pppoe_username` is unique globally, not per-router, so a subscriber cannot exist twice.

### 1.5 Data migration from `Clients`

The hard part. `Clients.ip` is one `CharField` labelled `"IP/UserName"` holding either
kind of value.

```python
def classify_connection(row):
    """Return ('static_ip', value) | ('pppoe', value) | ('unknown', value)."""
    raw = (row.ip or '').strip()
    if not raw:
        return ('unknown', raw)
    try:
        ipaddress.IPv4Address(raw)
        return ('static_ip', raw)
    except ValueError:
        pass
    if re.fullmatch(r'[A-Za-z0-9._-]{3,64}', raw):
        return ('pppoe', raw)
    return ('unknown', raw)
```

- [ ] Migrate every `Clients` row to `Subscriber`
- [ ] Write `unknown` rows to `notes/migration-unclassified.csv` for manual review —
      **do not guess**, and do not drop them
- [ ] Duplicate `ip` values will violate the new unique constraints; report rather than
      silently deduplicate
- [ ] `client_id` → `account_no` as a human-facing account number, no longer treated as a key
- [ ] `status` (`active`/`inactive`) → `service_state`: `active` → `ACTIVE`,
      `inactive` → `SUSPENDED`
- [ ] `expires_at` has no source data — set to `NULL` and leave subscribers in their
      migrated state until P6 records a first payment. **Do not backfill a fake date**;
      P7 would immediately suspend everyone.
- [ ] Migration must be reversible, and gated on a verified DB backup

### 1.6 Service state machine

The only permitted write path to `service_state`.

```python
# apps/subscribers/services.py

TRANSITIONS = {
    'pending':    {'active', 'terminated'},
    'active':     {'grace', 'suspended', 'terminated'},
    'grace':      {'active', 'suspended', 'terminated'},
    'suspended':  {'active', 'terminated'},
    'terminated': set(),
}

class InvalidTransition(Exception): ...

@transaction.atomic
def transition(sub, to_state, *, reason, actor=None, provision=True):
    if to_state not in TRANSITIONS[sub.service_state]:
        raise InvalidTransition(f"{sub.service_state} -> {to_state}")

    before = sub.service_state
    sub.service_state = to_state
    sub.sync_state = Subscriber.Sync.PENDING
    sub.save(update_fields=['service_state', 'sync_state', 'updated'])

    record_event(
        subject=sub, action='state_change',
        state_before=before, state_after=to_state,
        reason=reason, actor=actor, is_automatic=actor is None,
    )

    if provision:
        # imported lazily; no-ops until P5 lands
        provision_subscriber.delay(sub.pk)
```

- [ ] Implement with `provision_subscriber` as a no-op stub — P5 fills it in
- [ ] Unit tests for every legal and illegal transition
- [ ] Add a check (test or `pre_save` guard) that nothing outside `services.py` writes
      `service_state`

---

## Files touched

```
apps/subscribers/          new — replaces apps/clients
apps/billing/              new — Package moves here
apps/network/models.py     Router
apps/clients/              removed after migration verified
apps/packages/             removed after migration verified
```

## Exit criteria

- [ ] Every `Clients` row is either migrated or listed in `migration-unclassified.csv`
- [ ] State machine unit tests cover all transitions, legal and illegal
- [ ] `makemigrations --check` clean
- [ ] Router password round-trips through Fernet and never appears in a form render,
      log line, or `repr()`
- [ ] Still zero router code in the repo

## Risks

| Risk | Mitigation |
|------|------------|
| Ambiguous `ip` data misclassified | Report-and-review, never guess. Reversible migration. Backup gate. |
| Backfilling `expires_at` triggers mass suspension in P7 | Leave `NULL`. P7 must explicitly skip `NULL` expiry. |
| `CASCADE` → `PROTECT` breaks existing delete flows | Expected — those flows were silently destroying data. Update views to handle `ProtectedError` with a real message. |
| Unique constraints reject existing duplicate rows | Surface as a report before the migration runs, not as a failure during it |

## Out of scope

Invoices and payments (P6). Anything that talks to a router (P4+). UI for these models —
the existing admin is enough to verify the migration.
