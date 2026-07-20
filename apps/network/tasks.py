"""Network tasks.

heartbeat exists to prove the beat -> broker -> worker chain end to end in
staging before any real task depends on it. Router polling, provisioning,
and reconciliation land in P4/P5.
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def heartbeat():
    logger.info('celery heartbeat %s', timezone.now().isoformat())
    return 'ok'
