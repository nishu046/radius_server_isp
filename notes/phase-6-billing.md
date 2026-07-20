# Phase 6 — Billing & Payments

**Depends on:** P1
**Blocks:** P7
**Independent of all router work** — can run in parallel with P4/P5.

## Goal

Turn money received into an expiry date. Deliberately simple: prepaid periods, one invoice
per cycle, manual payment capture.

## Open decisions that block this phase

1. **Billing anchor** — does a cycle run from the payment date, or from a fixed calendar
   day of the month? Fixed-day is more work but far easier for collectors to plan routes
   around, and it makes revenue predictable. This changes `next_period_start()`.
2. **Partial payments** — does ৳600 against a ৳1,200 invoice restore service, or does
   restoration require settlement in full?

Both need answering before 6.3.

---

## Model

`expires_at` on the subscriber is a **derived** value. Recording a payment extends it by
`package.billing_cycle_days`. Nothing else moves it except an explicit manual adjustment,
which is logged as a `ServiceEvent`.

```python
class Subscription(models.Model):
    """One billing period for one subscriber."""
    subscriber   = models.ForeignKey(Subscriber, on_delete=models.PROTECT)
    package      = models.ForeignKey(Package, on_delete=models.PROTECT)

    period_start = models.DateTimeField()
    period_end   = models.DateTimeField()

    # snapshotted so a later price change never rewrites history
    price_charged = models.DecimalField(max_digits=10, decimal_places=2)

    created = models.DateTimeField(auto_now_add=True)


class Invoice(models.Model):
    class Status(models.TextChoices):
        UNPAID  = 'unpaid'
        PARTIAL = 'partial'
        PAID    = 'paid'
        VOID    = 'void'

    number       = models.CharField(max_length=30, unique=True)
    subscriber   = models.ForeignKey(Subscriber, on_delete=models.PROTECT)
    subscription = models.ForeignKey(Subscription, null=True, on_delete=models.PROTECT)

    issue_date = models.DateField()
    due_date   = models.DateField()
    subtotal   = models.DecimalField(max_digits=10, decimal_places=2)
    discount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total      = models.DecimalField(max_digits=10, decimal_places=2)
    status     = models.CharField(max_length=20, choices=Status, default=Status.UNPAID)

    class Meta:
        ordering = ['-issue_date', '-id']


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH   = 'cash'
        BKASH  = 'bkash'
        NAGAD  = 'nagad'
        BANK   = 'bank'
        ADJUST = 'adjustment'

    invoice     = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    method      = models.CharField(max_length=20, choices=Method)
    reference   = models.CharField(max_length=100, blank=True)   # bKash TRX id, etc.

    received_by = models.ForeignKey(User, on_delete=models.PROTECT)   # never editable
    received_at = models.DateTimeField(default=timezone.now)
    note        = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-received_at']
```

Design notes:

- **`price_charged` is snapshotted** on the subscription. Raising a package price must not
  retroactively change what a customer was billed last March.
- **All money is `Decimal`.** The existing `Package.price` is a `Float` and `Commission.profit`
  is a `Float` — both converted in P1.
- **`received_by` is never editable.** It is the accountability record for cash handling,
  and the reason a collector cannot quietly reassign a payment.
- **`PROTECT` everywhere.** Deleting a subscriber must not delete their payment history.
- No gateway integration. bKash and Nagad are recorded *methods* with a reference number
  the collector types in.

---

## Tasks

### 6.1 Models and migrations

- [ ] The three models above
- [ ] Invoice numbering — sequential per year, gapless, generated in a transaction
      (`ISP-2026-000412`). Gaps in invoice numbers are an accounting problem.
- [ ] Constraint: sum of payments cannot exceed invoice total without an explicit
      overpayment flag

### 6.2 Payment capture

The screen a collector uses at a customer's door. Built for a mid-range Android phone,
one-handed, possibly on a bad connection.

- [ ] Search by account no, phone, or name — tolerant of partial input
- [ ] Subscriber card showing balance due and current state
- [ ] Amount pre-filled with the outstanding balance
- [ ] Method selector, reference field shown only for non-cash
- [ ] Big confirm button; clear success state
- [ ] **Target: under 20 seconds from search to confirmation**
- [ ] Receipt view, printable and shareable
- [ ] Works on a slow connection — no large payloads, no blocking spinners

### 6.3 Applying a payment

```python
@transaction.atomic
def record_payment(invoice, amount, method, reference, actor):
    payment = Payment.objects.create(...)

    paid = invoice.payments.aggregate(s=Sum('amount'))['s'] or 0
    invoice.status = (
        Invoice.Status.PAID if paid >= invoice.total
        else Invoice.Status.PARTIAL if paid > 0
        else Invoice.Status.UNPAID
    )
    invoice.save(update_fields=['status'])

    if invoice.status == Invoice.Status.PAID:
        extend_service(invoice.subscriber, invoice.subscription)

    record_event(subject=invoice.subscriber, action='payment',
                 actor=actor, payload={'amount': str(amount), 'method': method})
    return payment
```

```python
def extend_service(sub, subscription):
    """Extend from the later of now and current expiry, so paying early
    does not lose the customer days they already bought."""
    base = max(timezone.now(), sub.expires_at or timezone.now())
    sub.expires_at = base + timedelta(days=sub.package.billing_cycle_days)
    sub.save(update_fields=['expires_at'])

    if sub.service_state in ('grace', 'suspended', 'pending'):
        transition(sub, 'active', reason='payment_received', actor=None)
```

- [ ] The `max(now, expires_at)` detail matters — extending from `now` silently steals days
      from customers who pay early
- [ ] Timezone: Asia/Dhaka, `USE_TZ = True`. No DST, which removes a whole class of bugs,
      but store UTC and convert at the edges regardless.
- [ ] Transition to `active` enqueues provisioning on the **priority queue** (P5/P7) so the
      collector sees reconnection before leaving

### 6.4 Invoice generation

- [ ] Beat task, daily: raise the next invoice for `auto_renew` subscribers approaching
      period end
- [ ] Lead time configurable (e.g. issue 5 days before expiry)
- [ ] Idempotent — running twice in a day does not produce two invoices
- [ ] Skip `terminated` subscribers

### 6.5 Reporting

- [ ] Arrears list: who owes what, how overdue, sorted by amount
- [ ] Collection sheet: subscribers due in the next N days, grouped by POP, for route planning
- [ ] Daily collection summary per collector — cash accountability
- [ ] Revenue by package, by POP, by month

### 6.6 Connect to the existing ledger

The current `Earning` model is freetext lines entered by hand.

- [ ] Payments post into `Earning` automatically
- [ ] Existing manual entries preserved and distinguishable from generated ones
- [ ] Reconciliation check: ledger total vs payment total, surfaced as a report

Without this, the accounting screens and the billing screens will disagree, and staff will
stop trusting both.

### 6.7 Billing UI

Deferred here from P3.

- [ ] Invoice list and detail
- [ ] Payment list, filterable by collector and date
- [ ] Subscriber billing panel: current period, balance, payment history
- [ ] All built from the P2 component vocabulary

---

## Files touched

```
apps/billing/models.py        Subscription, Invoice, Payment
apps/billing/services.py      record_payment, extend_service, generate_invoices
apps/billing/tasks.py         daily invoice generation
apps/billing/views.py         capture, invoices, payments, reports
apps/billing/templates/       billing screens
apps/accountants/             Earning integration
```

## Exit criteria

- [ ] Recording a payment extends `expires_at` correctly across month boundaries
- [ ] Paying early preserves remaining days (test asserts this explicitly)
- [ ] Invoice numbers are gapless and unique under concurrent creation
- [ ] Payment totals reconcile against the `Earning` ledger
- [ ] Collector flow completes in under 20s on a 360px viewport
- [ ] A payment cannot be edited or deleted, only reversed by an adjustment
- [ ] Money arithmetic uses `Decimal` end to end; no float anywhere in the path

## Risks

| Risk | Mitigation |
|------|------------|
| Float rounding in money | `Decimal` everywhere; convert legacy float fields in P1; test with amounts that expose float error |
| Extending from `now` steals customer days | `max(now, expires_at)`; explicit test |
| Duplicate invoices from a retried task | Idempotency key on (subscriber, period) |
| Invoice number gaps or collisions | Generated inside the transaction with a locked counter |
| Collector edits their own payment record | Payments immutable; corrections are adjustment entries with their own `received_by` |

## Out of scope

Online payment gateway integration. SMS or email notification of invoices. Tax handling
beyond a flat discount field. Subscriber self-service portal.
