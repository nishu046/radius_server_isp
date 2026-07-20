"""Subscriber — replaces apps.clients.Clients.

Three things changed from the old model and each one matters:

  * `ip`, a single CharField labelled "IP/UserName" holding either a static
    IP or a PPPoE username, splits into a typed connection.
  * `service_state` and `expires_at` appear, which is what the whole
    enforcement loop keys off.
  * Foreign keys become PROTECT/SET_NULL. The old model used CASCADE
    everywhere, so deleting a package deleted its subscribers and a damaged
    ONU deleted the customer.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.network.crypto import decrypt, encrypt


class Subscriber(models.Model):
    class Connection(models.TextChoices):
        PPPOE = 'pppoe', 'PPPoE'
        STATIC_IP = 'static_ip', 'Static IP'

    class State(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        GRACE = 'grace', 'Grace'
        SUSPENDED = 'suspended', 'Suspended'
        TERMINATED = 'terminated', 'Terminated'

    class Sync(models.TextChoices):
        SYNCED = 'synced', 'Synced'
        PENDING = 'pending', 'Pending'
        DRIFTED = 'drifted', 'Drifted'
        FAILED = 'failed', 'Failed'

    # identity
    account_no = models.CharField(
        max_length=30, unique=True,
        help_text='Human-facing account number shown to the customer.',
    )
    name = models.CharField(max_length=150)
    email = models.EmailField(max_length=150, blank=True)
    phone = models.CharField(max_length=30)
    nid = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=255)

    # connection
    connection_type = models.CharField(max_length=20, choices=Connection)
    pppoe_username = models.CharField(
        max_length=64, unique=True, null=True, blank=True,
        help_text='Unique across the whole system, not per router, so a '
                  'subscriber cannot exist twice.',
    )
    pppoe_password_enc = models.BinaryField(default=b'', editable=False)
    static_ip = models.GenericIPAddressField(
        protocol='IPv4', unique=True, null=True, blank=True)
    mac_address = models.CharField(
        max_length=17, blank=True,
        help_text='Optional ARP binding for static-IP subscribers.',
    )

    # service
    router = models.ForeignKey(
        'network.Router', on_delete=models.PROTECT, related_name='subscribers')
    package = models.ForeignKey(
        'billing.Package', on_delete=models.PROTECT, related_name='subscribers')
    onu = models.ForeignKey(
        'onu.Onu', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='subscribers')
    pop = models.ForeignKey(
        'pop.Pop', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='subscribers')

    service_state = models.CharField(
        max_length=20, choices=State, default=State.PENDING,
        help_text='Never assign directly — go through '
                  'apps.subscribers.services.transition().',
    )
    expires_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text='When paid service ends. NULL never expires — migrated '
                  'subscribers have no source data for this and must not be '
                  'suspended until a payment sets it.',
    )
    grace_days = models.PositiveIntegerField(
        default=3,
        help_text='Days of service after expiry before suspension.',
    )
    auto_renew = models.BooleanField(default=True)

    sync_state = models.CharField(
        max_length=20, choices=Sync, default=Sync.PENDING)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created', '-id']
        indexes = [
            models.Index(fields=['service_state', 'expires_at']),
            models.Index(fields=['sync_state']),
        ]
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

    def __str__(self):
        return f'{self.name} ({self.account_no})'

    # credentials
    def set_pppoe_password(self, plaintext):
        self.pppoe_password_enc = encrypt(plaintext)

    def get_pppoe_password(self):
        """Readable, not hashed — support staff read it back to customers."""
        return decrypt(self.pppoe_password_enc)

    # derived state
    @property
    def is_online_eligible(self):
        """Whether the router should currently be letting this user connect."""
        return self.service_state in (self.State.ACTIVE, self.State.GRACE)

    @property
    def suspend_at(self):
        """When grace ends. None if there is no expiry."""
        if self.expires_at is None:
            return None
        return self.expires_at + timezone.timedelta(days=self.grace_days)

    @property
    def days_until_expiry(self):
        if self.expires_at is None:
            return None
        return (self.expires_at - timezone.now()).days

    @property
    def connection_identifier(self):
        """What identifies this subscriber on the router."""
        if self.connection_type == self.Connection.PPPOE:
            return self.pppoe_username
        return self.static_ip

    @property
    def owned_comment(self):
        """Ownership tag written into the RouterOS comment field (P5).

        The reconciler only touches objects carrying this marker, which is
        what stops it deleting hand-built router config.
        """
        return f'ispms:sub:{self.pk}'
