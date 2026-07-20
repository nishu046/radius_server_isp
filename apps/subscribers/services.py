"""Service layer.

Every change to Subscriber.service_state goes through transition(). Nothing
else may write that field — it is the difference between an auditable system
and one where a customer's internet stops for reasons nobody can reconstruct.
"""

import logging
import secrets
import string

from django.db import transaction

from apps.network.models import record_event

from .models import Subscriber

logger = logging.getLogger(__name__)


# state -> states reachable from it
TRANSITIONS = {
    Subscriber.State.PENDING: {Subscriber.State.ACTIVE, Subscriber.State.TERMINATED},
    Subscriber.State.ACTIVE: {Subscriber.State.GRACE, Subscriber.State.SUSPENDED,
                              Subscriber.State.TERMINATED},
    Subscriber.State.GRACE: {Subscriber.State.ACTIVE, Subscriber.State.SUSPENDED,
                             Subscriber.State.TERMINATED},
    Subscriber.State.SUSPENDED: {Subscriber.State.ACTIVE, Subscriber.State.TERMINATED},
    Subscriber.State.TERMINATED: set(),
}


class InvalidTransition(Exception):
    """Raised when a state change is not permitted by TRANSITIONS."""


@transaction.atomic
def transition(subscriber, to_state, *, reason, actor=None, provision=True):
    """Move a subscriber to a new service state.

    actor=None means the change was automatic (the expiry sweep), which is
    recorded explicitly rather than inferred.

    Returns the ServiceEvent so callers can reference it.
    """
    from_state = subscriber.service_state

    if to_state == from_state:
        logger.debug('subscriber %s already in %s', subscriber.pk, to_state)
        return None

    allowed = TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise InvalidTransition(
            f'{subscriber} cannot go {from_state} -> {to_state}. '
            f'Allowed from {from_state}: {sorted(allowed) or "nothing"}.'
        )

    subscriber.service_state = to_state
    subscriber.sync_state = Subscriber.Sync.PENDING
    subscriber.save(update_fields=['service_state', 'sync_state', 'updated'])

    event = record_event(
        subject=subscriber,
        action='state_change',
        actor=actor,
        reason=reason,
        state_before=from_state,
        state_after=to_state,
    )

    if provision:
        _enqueue_provisioning(subscriber)

    return event


def _enqueue_provisioning(subscriber):
    """Hand the router work to a worker.

    A no-op until P5 lands the provisioning task. Router calls never happen
    inline — a slow or unreachable router must not block the request or stall
    the expiry sweep.
    """
    try:
        from apps.network.tasks import provision_subscriber
    except ImportError:
        logger.debug('provisioning not implemented yet (P5); skipping')
        return

    transaction.on_commit(lambda: provision_subscriber.delay(subscriber.pk))


def generate_pppoe_password(length=12):
    """Readable-ish password — support staff read these over the phone.

    Excludes characters that get misheard or mistyped: 0/O, 1/l/I.
    """
    alphabet = (
        ''.join(c for c in string.ascii_lowercase if c not in 'l')
        + ''.join(c for c in string.ascii_uppercase if c not in 'IO')
        + ''.join(c for c in string.digits if c not in '01')
    )
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_account_no():
    """Sequential account number, gapless enough for customer reference."""
    last = Subscriber.objects.order_by('-id').values_list('account_no', flat=True).first()
    if last and last.isdigit():
        return str(int(last) + 1)
    return '1001'
