"""Network app models.

Holds ServiceEvent now; Router, RouterSnapshot and ProvisioningJob land in
P1/P4/P5.
"""

from django.conf import settings
from django.db import models


class ServiceEventQuerySet(models.QuerySet):
    def for_subject(self, obj):
        return self.filter(
            subject_type=obj._meta.model_name,
            subject_id=obj.pk,
        )


class ServiceEventManager(models.Manager.from_queryset(ServiceEventQuerySet)):
    """Append-only.

    An audit trail that can be edited is not an audit trail. update() and
    delete() are blocked at the manager and queryset level so a stray
    .update() in a later phase fails loudly instead of quietly rewriting
    history.
    """

    def get_queryset(self):
        return super().get_queryset()


class ServiceEvent(models.Model):
    """One recorded action against a subscriber, router, or invoice.

    Written by every service-layer transition. When a customer disputes a
    disconnection, this table is the answer — which is why it exists in P0,
    before anything can change service state, rather than being bolted on
    after the first weeks of production have no history.
    """

    # who
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text='Null when the action was automatic.',
    )
    is_automatic = models.BooleanField(default=False)

    # what it happened to — generic by (type, id) rather than a
    # GenericForeignKey, so the row survives the subject being deleted
    subject_type = models.CharField(max_length=50)
    subject_id = models.IntegerField()
    subject_label = models.CharField(
        max_length=200, blank=True,
        help_text='Human-readable subject at the time, kept for when the '
                  'subject is later deleted or renamed.',
    )

    # what happened
    action = models.CharField(max_length=50)
    state_before = models.CharField(max_length=30, blank=True)
    state_after = models.CharField(max_length=30, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    succeeded = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = ServiceEventManager()

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['subject_type', 'subject_id', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        who = self.actor or 'system'
        return f'{self.action} {self.subject_type}#{self.subject_id} by {who}'

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError('ServiceEvent is append-only and cannot be modified.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('ServiceEvent is append-only and cannot be deleted.')


def record_event(*, subject, action, actor=None, reason='', payload=None,
                 state_before='', state_after='', succeeded=True):
    """Write an audit row.

    actor=None means the action was automatic, which is recorded explicitly
    rather than inferred — the subscriber timeline distinguishes "the system
    did this" from "a named person did this", and that distinction is the
    whole point of the log.
    """
    return ServiceEvent.objects.create(
        actor=actor,
        is_automatic=actor is None,
        subject_type=subject._meta.model_name,
        subject_id=subject.pk,
        subject_label=str(subject)[:200],
        action=action,
        state_before=state_before or '',
        state_after=state_after or '',
        reason=reason,
        payload=payload or {},
        succeeded=succeeded,
    )
