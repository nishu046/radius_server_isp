"""Authorization tests.

These exist because the original implementation had two holes:

  1. has_perm()/has_module_perms() returned True unconditionally, so every
     authenticated account was a full administrator.
  2. apps/users/views.py had no login_required at all, so an anonymous request
     could list, create, and DELETE users. Deletion was a GET, so it needed no
     CSRF token and could be triggered by an <img> tag.

Both are regressions worth failing loudly on.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .roles import sync_roles

User = get_user_model()


class AnonymousAccessTests(TestCase):
    """No unauthenticated request may reach user management."""

    def setUp(self):
        self.victim = User.objects.create_user('victim@example.com', 'pw-Str0ng!23')

    def test_user_list_requires_login(self):
        response = self.client.get(reverse('user'))
        self.assertNotEqual(response.status_code, 200)

    def test_user_create_requires_login(self):
        response = self.client.get(reverse('create-user'))
        self.assertNotEqual(response.status_code, 200)

    def test_anonymous_cannot_delete_user(self):
        self.client.post(reverse('user-delete', args=[self.victim.pk]))
        self.assertTrue(User.objects.filter(pk=self.victim.pk).exists())

    def test_delete_rejects_get(self):
        """Deletion must not be reachable by navigation or an image tag."""
        response = self.client.get(reverse('user-delete', args=[self.victim.pk]))
        self.assertIn(response.status_code, (302, 403, 405))
        self.assertTrue(User.objects.filter(pk=self.victim.pk).exists())


class PermissionEnforcementTests(TestCase):
    """A logged-in user is not automatically an administrator."""

    def setUp(self):
        sync_roles()
        self.collector = User.objects.create_user('collector@example.com', 'pw-Str0ng!23')
        self.collector.groups.add(Group.objects.get(name='collector'))
        self.victim = User.objects.create_user('victim@example.com', 'pw-Str0ng!23')

    def test_has_perm_is_not_unconditionally_true(self):
        self.assertFalse(self.collector.has_perm('users.delete_user'))
        self.assertFalse(self.collector.has_perm('accountants.change_commission'))

    def test_has_module_perms_is_not_unconditionally_true(self):
        self.assertFalse(self.collector.has_module_perms('accountants'))

    def test_collector_cannot_delete_user(self):
        self.client.force_login(self.collector)
        response = self.client.post(reverse('user-delete', args=[self.victim.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.victim.pk).exists())

    def test_collector_cannot_reach_admin(self):
        self.client.force_login(self.collector)
        response = self.client.get('/admin/', follow=True)
        self.assertNotContains(response, 'Site administration', status_code=200)

    def test_collector_keeps_granted_permission(self):
        """The narrowing must not remove what the role legitimately needs."""
        self.assertTrue(self.collector.has_perm('subscribers.view_subscriber'))

    def test_collector_cannot_change_subscribers(self):
        """Recording a payment and cutting off a customer are not the same
        trust level, so they are never the same permission."""
        self.assertFalse(self.collector.has_perm('subscribers.change_subscriber'))
        self.assertFalse(self.collector.has_perm('network.change_router'))

    def test_superuser_retains_access(self):
        admin = User.objects.create_superuser('root@example.com', 'pw-Str0ng!23')
        self.assertTrue(admin.has_perm('users.delete_user'))
        self.assertTrue(admin.has_module_perms('accountants'))


class SelfDeletionTests(TestCase):
    def test_user_cannot_delete_own_account(self):
        admin = User.objects.create_superuser('root@example.com', 'pw-Str0ng!23')
        self.client.force_login(admin)
        self.client.post(reverse('user-delete', args=[admin.pk]))
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())


class RoleMigrationTests(TestCase):
    def test_sync_roles_is_idempotent(self):
        sync_roles()
        first = Group.objects.get(name='manager').permissions.count()
        sync_roles()
        self.assertEqual(Group.objects.get(name='manager').permissions.count(), first)
        self.assertEqual(Group.objects.filter(name='manager').count(), 1)

    def test_all_four_roles_exist(self):
        sync_roles()
        for name in ('owner', 'manager', 'collector', 'technician'):
            self.assertTrue(Group.objects.filter(name=name).exists(), name)


class PasswordValidationTests(TestCase):
    def test_weak_password_rejected_on_register(self):
        from .forms import RegisterForm

        form = RegisterForm(data={
            'email': 'weak@example.com',
            'first_name': 'A', 'last_name': 'B', 'gender': 'x',
            'password': '123', 'password2': '123',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)
