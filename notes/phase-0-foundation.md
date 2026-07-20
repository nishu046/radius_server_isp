# Phase 0 — Foundation & Security

**Depends on:** nothing. Start immediately.
**Blocks:** everything.
**Ships no features.**

## Goal

Make the existing app safe, and capable of supporting background workers. Every task here
is either a live defect or infrastructure that later phases assume exists.

## Why this is first

Phase 7 gives this software the ability to cut off a customer's internet. An authorization
hole at that point means any account can disconnect your entire customer base. The
permissions bug is not a cleanup item — it is a prerequisite for being allowed to build
the rest.

---

## Tasks

### 0.1 Fix authorization

`apps/users/models.py` currently has:

```python
def has_perm(self, perm, obj=None):
    return True          # every user is authorized for everything

def has_module_perms(self, app_label):
    return True
```

Replace with Django's real permission framework.

- [ ] Add `PermissionsMixin` to the `User` model, or implement `has_perm` against groups
- [ ] Keep `is_staff` / `is_superuser` but drive them from real fields, not the current
      `staff`/`admin` boolean pair shadowing them
- [ ] Create four groups matching the roles: `owner`, `manager`, `collector`, `technician`
- [ ] Define custom permissions that later phases need:
      `subscribers.suspend_subscriber`, `subscribers.terminate_subscriber`,
      `subscribers.change_package`, `billing.waive_invoice`, `network.change_router_credentials`
- [ ] Data migration assigning existing users to groups based on current
      `owner`/`employs`/`staff`/`admin` flags
- [ ] Replace the `apps/users/decorator.py` and `apps/accountants/decorator.py` checks with
      permission-based ones

**Test that proves it:** a user in `collector` gets 403 on the admin index and on a
subscriber delete view.

### 0.2 PostgreSQL

SQLite will not survive concurrent Celery workers writing provisioning state, and P7 needs
`select_for_update(skip_locked=True)` which SQLite does not support.

- [ ] Add `psycopg[binary]` to requirements
- [ ] Docker Compose for local Postgres 16 + Redis
- [ ] Move DB config to `DATABASES` driven by `DATABASE_URL` via `python-decouple`
- [ ] Migrate existing dev data (or accept a fresh DB — it is only the dev superuser today)
- [ ] Confirm `makemigrations --check` still reports no drift on Postgres

### 0.3 Audit log

This must exist before anything can change service state. Retrofitting an audit trail
after the fact means the first weeks of production have no history.

- [ ] Create `apps.network` app (it will hold routers later; the audit model lives here now)
- [ ] `ServiceEvent` model — append-only, never updated or deleted:

```python
class ServiceEvent(models.Model):
    # who
    actor       = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    is_automatic = models.BooleanField(default=False)

    # what
    subject_type = models.CharField(max_length=50)   # 'subscriber', 'router', 'invoice'
    subject_id   = models.IntegerField()
    action       = models.CharField(max_length=50)   # 'suspend', 'provision', 'payment'

    # detail
    state_before = models.CharField(max_length=30, blank=True)
    state_after  = models.CharField(max_length=30, blank=True)
    reason       = models.CharField(max_length=200, blank=True)
    payload      = models.JSONField(default=dict)    # raw router response, request data
    succeeded    = models.BooleanField(default=True)

    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['subject_type', 'subject_id', '-created_at'])]
```

- [ ] Helper `record_event(...)` used by every service-layer function from P1 onward
- [ ] No `update()` or `delete()` path — enforce at the manager level

### 0.4 Celery + Redis

- [ ] Add `celery`, `redis`, `django-celery-beat` to requirements
- [ ] `isp_management/celery.py` with app config, autodiscovery
- [ ] Separate queues defined now, used later: `default`, `provisioning`, `priority`
- [ ] One trivial beat task (`heartbeat` writing a log line every minute) to prove the
      whole chain works in staging
- [ ] Worker + beat in Docker Compose

**Exit for this task:** beat fires the heartbeat on a staging box for an hour without
intervention.

### 0.5 Pagination ordering bug

Every list view triggers `UnorderedObjectListWarning`. This is a real user-visible bug —
paginating an unordered queryset means rows can repeat on page 2 or never appear at all.

- [ ] Add `Meta.ordering` to: `Clients`, `Onu`, `Pop`, `Tasks`, `Warehouse`, `Package`,
      `Employ`, `Invest`, `Earning`, `Commission`
- [ ] Use a deterministic, unique-suffixed ordering (`['-created', '-id']`) — ordering by a
      non-unique field alone has the same problem
- [ ] Confirm zero warnings: `python -W error::UserWarning manage.py test`

Affected views for reference:

```
apps/clients/views.py:23      apps/onu/views.py:23
apps/pop/views.py:23          apps/tasks/views.py:24
apps/warehouse/views.py:68
```

### 0.6 Template directory casing

`apps/clients/Templates/` and `apps/onu/Templates/` use a capital T. These work on the
current macOS case-insensitive filesystem and **fail on Linux**.

- [ ] Rename via `git mv` in two steps (`Templates` → `templates_tmp` → `templates`) so git
      records the case change
- [ ] Grep for any hardcoded `Templates/` path references

### 0.7 Deployment settings

- [ ] Split settings into `base` / `dev` / `prod`
- [ ] `ALLOWED_HOSTS` from environment, not `['*']`
- [ ] Add `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
      `CSRF_COOKIE_SECURE`, `X_FRAME_OPTIONS` for prod
- [ ] Confirm `manage.py check --deploy` is clean
- [ ] Delete the dev superuser `admin@example.com` from any non-local environment

---

## Files touched

```
isp_management/settings/          new — split from settings.py
isp_management/celery.py          new
apps/network/                     new app — ServiceEvent only for now
apps/users/models.py              permissions rework
apps/users/decorator.py           permission-based
apps/accountants/decorator.py     permission-based
apps/*/models.py                  Meta.ordering
apps/clients/Templates/           → templates/
apps/onu/Templates/               → templates/
docker-compose.yml                new — postgres, redis, worker, beat
requirements.txt                  psycopg, celery, redis, django-celery-beat
```

## Exit criteria

- [ ] A `collector`-group user is provably blocked from Django admin and from a
      subscriber delete view (test asserts 403)
- [ ] App runs on PostgreSQL, `makemigrations --check` clean
- [ ] Celery beat runs a scheduled task in staging for an hour unattended
- [ ] `ServiceEvent` rows written on model changes
- [ ] Zero `UnorderedObjectListWarning` under `-W error`
- [ ] `manage.py check --deploy` clean

## Risks

| Risk | Mitigation |
|------|------------|
| Permission rework locks out existing users | Data migration assigns groups from current flags; verify each existing user can still log in and reach their screens before merging |
| Postgres migration loses dev data | Only the dev superuser exists today — acceptable to start fresh. Take a dump anyway. |
| Template rename lost on case-insensitive FS | Two-step `git mv`; verify with `git show --stat` that the rename is recorded |

## Out of scope

No new features, no UI changes, no router code. If a task here feels like it is growing
into a feature, it belongs in a later phase.
