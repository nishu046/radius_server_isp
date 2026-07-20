"""Billing models.

Package lives here now (moved from apps.packages). Subscription, Invoice
and Payment arrive in P6.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class Package(models.Model):
    """A service plan.

    Replaces apps.packages.Package, whose `speed` was a single integer.
    RouterOS rate limits need upload and download separately, and billing
    needs a cycle length to turn a payment into an expiry date.
    """

    name = models.CharField(max_length=100, unique=True)

    download_kbps = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Subscriber download rate in kbps.',
    )
    upload_kbps = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Subscriber upload rate in kbps.',
    )
    burst_download_kbps = models.PositiveIntegerField(null=True, blank=True)
    burst_upload_kbps = models.PositiveIntegerField(null=True, blank=True)

    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    billing_cycle_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        help_text='Days of service one payment buys.',
    )

    is_active = models.BooleanField(
        default=True,
        help_text='Inactive packages cannot be assigned to new subscribers.',
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['download_kbps', 'name', 'id']

    def __str__(self):
        return self.name

    @property
    def profile_name(self) -> str:
        """Name of the mirrored PPP profile on each router.

        Packages are mirrored as PPP profiles and secrets point at them, so
        changing a package's speed is one profile edit per router instead of
        one edit per subscriber. See notes/phase-5-provisioning.md.
        """
        return f'ispms-{slugify(self.name)}'

    @property
    def rate_limit(self) -> str:
        """RouterOS rate-limit string.

        The format is rx/tx FROM THE ROUTER'S POINT OF VIEW: rx is what the
        subscriber uploads, tx is what they download. Reversing these ships
        everyone a fast upload and a slow download, and it gets reported as
        "the internet is slow", not as a config bug.

        Built here and only here. See test_rate_limit_direction.
        """
        return f'{self.upload_kbps}k/{self.download_kbps}k'

    @property
    def download_mbps(self) -> float:
        return self.download_kbps / 1000

    @property
    def upload_mbps(self) -> float:
        return self.upload_kbps / 1000
