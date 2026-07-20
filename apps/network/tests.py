from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.packages.models import Package

from .models import ServiceEvent, record_event

User = get_user_model()


class AppendOnlyTests(TestCase):
    """An audit trail that can be edited is not an audit trail."""

    def setUp(self):
        self.package = Package.objects.create(name='Home 10M', speed=10, price=1200)

    def test_event_cannot_be_modified(self):
        event = record_event(subject=self.package, action='created')
        event.action = 'tampered'
        with self.assertRaises(ValueError):
            event.save()

    def test_event_cannot_be_deleted(self):
        event = record_event(subject=self.package, action='created')
        with self.assertRaises(ValueError):
            event.delete()

    def test_automatic_is_inferred_from_missing_actor(self):
        event = record_event(subject=self.package, action='expired')
        self.assertTrue(event.is_automatic)

    def test_actor_marks_event_as_manual(self):
        user = User.objects.create_user('m@example.com', 'pw-Str0ng!23')
        event = record_event(subject=self.package, action='suspend', actor=user)
        self.assertFalse(event.is_automatic)
        self.assertEqual(event.actor, user)

    def test_subject_label_survives_subject_deletion(self):
        record_event(subject=self.package, action='created')
        self.package.delete()

        event = ServiceEvent.objects.first()
        self.assertEqual(event.subject_label, 'Home 10M')
        self.assertEqual(event.subject_type, 'package')

    def test_for_subject_filters_correctly(self):
        other = Package.objects.create(name='Home 20M', speed=20, price=2000)
        record_event(subject=self.package, action='created')
        record_event(subject=other, action='created')

        self.assertEqual(ServiceEvent.objects.for_subject(self.package).count(), 1)


class HeartbeatTests(TestCase):
    def test_heartbeat_runs(self):
        from .tasks import heartbeat

        self.assertEqual(heartbeat.apply().get(), 'ok')
