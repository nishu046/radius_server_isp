"""Pagination integrity.

The original app paginated unordered querysets, so rows could appear on two
pages or on none. Meta.ordering fixed it, and annotate() quietly reintroduced
it in the billing view. This walks every page and asserts each row is seen
exactly once — the only check that actually catches the bug.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.billing.models import Package
from apps.network.models import Router

from .models import Subscriber

User = get_user_model()

TEST_KEY = 'Xzvm28uurts1tnEdyEt3hqZjDrUZK8st2st0DuevKJc='


@override_settings(ROUTER_CRED_KEY=TEST_KEY)
class PaginationIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('root@example.com', 'pw-Str0ng!23')
        router = Router.objects.create(name='r1', host='10.0.0.1', username='api')
        package = Package.objects.create(
            name='Home 10M', download_kbps=10000, upload_kbps=5000, price='1000')

        # more than two pages, and enough sharing a created timestamp that a
        # non-unique ordering would produce unstable pages
        Subscriber.objects.bulk_create([
            Subscriber(
                account_no=str(5000 + i),
                name=f'Sub {i}', phone='017', address='Dhaka',
                connection_type=Subscriber.Connection.PPPOE,
                pppoe_username=f'user{i}',
                router=router, package=package,
                service_state=Subscriber.State.ACTIVE,
            )
            for i in range(120)
        ])

    def setUp(self):
        self.client.force_login(self.admin)

    def test_every_row_appears_exactly_once_across_pages(self):
        url = reverse('subscribers:list')
        first = self.client.get(url)
        paginator = first.context['page_obj'].paginator

        self.assertGreater(paginator.num_pages, 2, 'need multiple pages to be meaningful')

        seen = []
        for number in range(1, paginator.num_pages + 1):
            page = self.client.get(url, {'page': number}).context['page_obj']
            seen.extend(sub.pk for sub in page.object_list)

        self.assertEqual(len(seen), paginator.count)
        self.assertEqual(len(set(seen)), paginator.count,
                         'a subscriber appeared on more than one page')

    def test_queryset_reports_as_ordered(self):
        """Django's Paginator warns when this is False, and a grouped
        queryset reports False even with Meta.ordering set."""
        response = self.client.get(reverse('subscribers:list'))
        self.assertTrue(response.context['page_obj'].paginator.object_list.ordered)

    def test_package_list_is_ordered_despite_annotate(self):
        response = self.client.get(reverse('billing:packages'))
        self.assertTrue(response.context['page_obj'].paginator.object_list.ordered)

    def test_filter_narrows_the_count(self):
        Subscriber.objects.filter(account_no__lt='5010').update(
            service_state=Subscriber.State.SUSPENDED)
        response = self.client.get(reverse('subscribers:list'),
                                   {'service_state': 'suspended'})
        self.assertEqual(response.context['page_obj'].paginator.count, 10)

    def test_search_matches_across_identifiers(self):
        url = reverse('subscribers:list')
        self.assertEqual(
            self.client.get(url, {'q': 'user7'}).context['page_obj'].paginator.count,
            # user7, user70..user79
            11,
        )

    def test_filters_survive_pagination(self):
        Subscriber.objects.filter(account_no__lt='5060').update(
            service_state=Subscriber.State.SUSPENDED)
        response = self.client.get(reverse('subscribers:list'),
                                   {'service_state': 'suspended', 'page': 2})
        page = response.context['page_obj']
        self.assertEqual(page.number, 2)
        for sub in page.object_list:
            self.assertEqual(sub.service_state, Subscriber.State.SUSPENDED)
