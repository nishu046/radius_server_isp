"""Celery application.

Queues, declared here and used by later phases:

  default      — everything unclassified
  provisioning — bulk router writes and reconciliation (P5). Rate-limited
                 per router so a bulk run cannot saturate a CPU-limited
                 RouterOS device and take a POP offline.
  priority     — doorstep reconnections after a payment (P7). Jumps ahead
                 of bulk work because a person is standing there waiting.
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_management.settings.dev')

app = Celery('isp_management')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
