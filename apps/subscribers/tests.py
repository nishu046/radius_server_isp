from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import Package
from apps.network.models import Router, ServiceEvent

from .models import Subscriber
from .services import InvalidTransition, generate_pppoe_password, transition

User = get_user_model()

# a throwaway Fernet key so credential round-trips are testable.
# Test-only — never used for real router credentials.
TEST_KEY = 'Xzvm28uurts1tnEdyEt3hqZjDrUZK8st2st0DuevKJc='


def make_router(**kw):
    defaults = dict(name='lab-1', host='10.0.0.1', username='api')
    return Router.objects.create(**{**defaults, **kw})


def make_package(**kw):
    defaults = dict(name='Home 10M', download_kbps=10000,
                    upload_kbps=2000, price='1200.00')
    return Package.objects.create(**{**defaults, **kw})


def make_subscriber(**kw):
    defaults = dict(
        account_no='1001', name='Test Sub', phone='0170000000',
        address='Dhaka', connection_type=Subscriber.Connection.PPPOE,
        pppoe_username='test.sub',
    )
    defaults.setdefault('router', make_router())
    defaults.setdefault('package', make_package())
    return Subscriber.objects.create(**{**defaults, **kw})


class RateLimitTests(TestCase):
    """RouterOS rate-limit is rx/tx from the ROUTER's point of view.

    rx is the subscriber's upload, tx is their download. Reversing these
    ships everyone a fast upload and a slow download, and it gets reported
    as "the internet is slow", not as a config bug.
    """

    def test_rate_limit_direction(self):
        package = make_package(download_kbps=10000, upload_kbps=2000)
        self.assertEqual(package.rate_limit, '2000k/10000k')

    def test_rate_limit_upload_comes_first(self):
        package = make_package(download_kbps=50000, upload_kbps=5000)
        upload_part, download_part = package.rate_limit.split('/')
        self.assertEqual(upload_part, '5000k')
        self.assertEqual(download_part, '50000k')

    def test_profile_name_is_slugified(self):
        self.assertEqual(make_package(name='Home 10M').profile_name, 'ispms-home-10m')


class StateMachineTests(TestCase):
    def setUp(self):
        self.sub = make_subscriber()
        self.actor = User.objects.create_user('m@example.com', 'pw-Str0ng!23')

    def test_pending_to_active(self):
        transition(self.sub, Subscriber.State.ACTIVE,
                   reason='first payment', actor=self.actor)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.service_state, Subscriber.State.ACTIVE)

    def test_illegal_transition_raises(self):
        with self.assertRaises(InvalidTransition):
            transition(self.sub, Subscriber.State.GRACE, reason='nope')

    def test_terminated_is_terminal(self):
        transition(self.sub, Subscriber.State.TERMINATED, reason='closed')
        self.sub.refresh_from_db()
        for target in (Subscriber.State.ACTIVE, Subscriber.State.GRACE,
                       Subscriber.State.SUSPENDED):
            with self.assertRaises(InvalidTransition):
                transition(self.sub, target, reason='reopen')

    def test_transition_writes_audit_event(self):
        transition(self.sub, Subscriber.State.ACTIVE,
                   reason='first payment', actor=self.actor)
        event = ServiceEvent.objects.for_subject(self.sub).first()
        self.assertEqual(event.action, 'state_change')
        self.assertEqual(event.state_before, Subscriber.State.PENDING)
        self.assertEqual(event.state_after, Subscriber.State.ACTIVE)
        self.assertEqual(event.actor, self.actor)
        self.assertFalse(event.is_automatic)

    def test_automatic_transition_has_no_actor(self):
        transition(self.sub, Subscriber.State.ACTIVE, reason='payment')
        transition(self.sub, Subscriber.State.GRACE, reason='expired')
        event = ServiceEvent.objects.for_subject(self.sub).first()
        self.assertTrue(event.is_automatic)
        self.assertIsNone(event.actor)

    def test_transition_marks_sync_pending(self):
        self.sub.sync_state = Subscriber.Sync.SYNCED
        self.sub.save(update_fields=['sync_state'])
        transition(self.sub, Subscriber.State.ACTIVE, reason='payment')
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.sync_state, Subscriber.Sync.PENDING)

    def test_same_state_is_a_noop(self):
        self.assertIsNone(
            transition(self.sub, Subscriber.State.PENDING, reason='again'))

    def test_full_expiry_cycle(self):
        for target in (Subscriber.State.ACTIVE, Subscriber.State.GRACE,
                       Subscriber.State.SUSPENDED, Subscriber.State.ACTIVE):
            transition(self.sub, target, reason='cycle')
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.service_state, Subscriber.State.ACTIVE)


class ConnectionConstraintTests(TestCase):
    def test_pppoe_without_username_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subscriber.objects.create(
                account_no='2001', name='Bad', phone='017', address='x',
                connection_type=Subscriber.Connection.PPPOE,
                pppoe_username=None,
                router=make_router(), package=make_package(),
            )

    def test_static_without_ip_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subscriber.objects.create(
                account_no='2002', name='Bad', phone='017', address='x',
                connection_type=Subscriber.Connection.STATIC_IP,
                static_ip=None,
                router=make_router(), package=make_package(),
            )

    def test_pppoe_username_unique_across_routers(self):
        make_subscriber(pppoe_username='dupe', account_no='3001')
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_subscriber(
                pppoe_username='dupe', account_no='3002',
                router=make_router(name='lab-2', host='10.0.0.2'),
            )


class ProtectedDeleteTests(TestCase):
    """The old model used CASCADE, so deleting a package deleted its
    subscribers and a damaged ONU deleted the customer."""

    def test_package_delete_is_protected(self):
        sub = make_subscriber()
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            sub.package.delete()

    def test_router_delete_is_protected(self):
        sub = make_subscriber()
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            sub.router.delete()


class DerivedStateTests(TestCase):
    def test_null_expiry_has_no_suspend_date(self):
        """NULL must never expire — migrated rows have no source data, and
        inventing one would suspend the whole customer base."""
        sub = make_subscriber(expires_at=None)
        self.assertIsNone(sub.suspend_at)
        self.assertIsNone(sub.days_until_expiry)

    def test_suspend_at_adds_grace(self):
        now = timezone.now()
        sub = make_subscriber(expires_at=now, grace_days=3)
        self.assertEqual(sub.suspend_at, now + timedelta(days=3))

    def test_grace_is_still_online_eligible(self):
        sub = make_subscriber(service_state=Subscriber.State.GRACE)
        self.assertTrue(sub.is_online_eligible)

    def test_suspended_is_not_online_eligible(self):
        sub = make_subscriber(service_state=Subscriber.State.SUSPENDED)
        self.assertFalse(sub.is_online_eligible)

    def test_owned_comment_format(self):
        sub = make_subscriber()
        self.assertEqual(sub.owned_comment, f'ispms:sub:{sub.pk}')


@override_settings(ROUTER_CRED_KEY=TEST_KEY)
class CredentialTests(TestCase):
    def test_router_password_round_trips(self):
        router = make_router()
        router.set_password('s3cret-api-pw')
        router.save()
        self.assertEqual(Router.objects.get(pk=router.pk).get_password(), 's3cret-api-pw')

    def test_router_password_not_stored_in_plaintext(self):
        router = make_router()
        router.set_password('s3cret-api-pw')
        router.save()
        self.assertNotIn(b's3cret-api-pw', bytes(router.password_enc))

    def test_repr_does_not_leak_credentials(self):
        router = make_router()
        router.set_password('s3cret-api-pw')
        self.assertNotIn('s3cret-api-pw', repr(router))

    def test_pppoe_password_round_trips(self):
        sub = make_subscriber()
        sub.set_pppoe_password('cust0mer-pw')
        sub.save()
        self.assertEqual(Subscriber.objects.get(pk=sub.pk).get_pppoe_password(),
                         'cust0mer-pw')


class PasswordGeneratorTests(TestCase):
    def test_excludes_confusable_characters(self):
        for _ in range(50):
            pw = generate_pppoe_password()
            self.assertFalse(set(pw) & set('0O1lI'), f'confusable char in {pw}')

    def test_length(self):
        self.assertEqual(len(generate_pppoe_password(16)), 16)


class ClientClassificationTests(TestCase):
    """The migration must not guess at ambiguous Clients.ip values."""

    def test_classification(self):
        import importlib
        mod = importlib.import_module(
            'apps.subscribers.migrations.0002_migrate_from_clients')
        classify = mod.classify

        self.assertEqual(classify('192.168.1.50'), ('static_ip', '192.168.1.50'))
        self.assertEqual(classify('rahman.k'), ('pppoe', 'rahman.k'))
        self.assertEqual(classify('user_01@isp'), ('pppoe', 'user_01@isp'))
        self.assertEqual(classify('')[0], 'unknown')
        self.assertEqual(classify('   ')[0], 'unknown')
        self.assertEqual(classify('has spaces')[0], 'unknown')
        self.assertEqual(classify('999.999.999.999')[0], 'unknown')
        self.assertEqual(classify('ab')[0], 'unknown')
