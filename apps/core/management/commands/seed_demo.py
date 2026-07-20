"""Generate realistic demo data for development.

Refuses to run when DEBUG is False. Seed data in production would be
indistinguishable from real subscribers, and a fake subscriber that later
gets provisioned onto a router is a genuine outage.

    manage.py seed_demo                  # 400 subscribers
    manage.py seed_demo --subscribers 60
    manage.py seed_demo --flush          # clear demo data first
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accountants.models import Earning, Invest
from apps.billing.models import Package
from apps.employ.models import Employ, EmployCategory
from apps.network.models import Router, ServiceEvent, record_event
from apps.onu.models import Onu
from apps.pop.models import Pop
from apps.subscribers.models import Subscriber
from apps.subscribers.services import generate_pppoe_password
from apps.tasks.models import TaskCategory, Tasks
from apps.users.models import User
from apps.warehouse.models import Warehouse, WarehouseCategory

FIRST_NAMES = [
    'Kamrul', 'Nasrin', 'Imran', 'Sabina', 'Rafiq', 'Tahmina', 'Jahangir',
    'Rumana', 'Shahidul', 'Farzana', 'Mizanur', 'Shirin', 'Aminul', 'Rehana',
    'Habibur', 'Nusrat', 'Delwar', 'Sultana', 'Moshiur', 'Ayesha', 'Anwar',
    'Rokeya', 'Bashir', 'Munira', 'Tanvir', 'Shabnam', 'Faisal', 'Dilruba',
    'Zahid', 'Sharmin', 'Rashed', 'Marufa', 'Sohel', 'Nadia', 'Arif', 'Lubna',
]

LAST_NAMES = [
    'Rahman', 'Hossain', 'Islam', 'Ahmed', 'Khan', 'Chowdhury', 'Akter',
    'Begum', 'Uddin', 'Haque', 'Ali', 'Sarker', 'Mia', 'Bhuiyan', 'Talukder',
    'Molla', 'Sheikh', 'Mondal', 'Das', 'Roy',
]

AREAS = [
    'Uttara Sector 7', 'Mirpur 10', 'Mirpur DOHS', 'Dhanmondi 27', 'Banani',
    'Gulshan 2', 'Bashundhara R/A', 'Mohammadpur', 'Badda', 'Rampura',
    'Savar Bazar', 'Tongi', 'Khilkhet', 'Baridhara', 'Shyamoli',
]

ONU_BRANDS = [('VSOL', 'V2802RH'), ('TP-Link', 'XZ000-G3'),
              ('Huawei', 'HG8310M'), ('ZTE', 'F660'), ('Netlink', 'HG323DAC')]

STOCK = [('MikroTik', 'hEX S'), ('MikroTik', 'CCR2004'), ('TP-Link', 'TL-SG1008'),
         ('Cisco', 'SG250-08'), ('Ubiquiti', 'UniFi AC LR'), ('D-Link', 'DGS-1100')]

TASK_TITLES = [
    'New connection installation', 'Fiber cut on distribution line',
    'ONU replacement', 'Speed complaint investigation', 'Router reconfiguration',
    'Shifting connection to new address', 'Splitter port fault',
    'Intermittent disconnection', 'Cable re-routing after roadwork',
    'Signal drop at customer premises',
]


class Command(BaseCommand):
    help = 'Generate realistic demo data (development only).'

    def add_arguments(self, parser):
        parser.add_argument('--subscribers', type=int, default=400)
        parser.add_argument('--flush', action='store_true',
                            help='Delete existing demo data first.')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'seed_demo refuses to run with DEBUG=False. Fake subscribers in '
                'production are indistinguishable from real ones, and one that '
                'gets provisioned onto a router is a real outage.'
            )

        random.seed(20260720)  # reproducible runs

        if options['flush']:
            self.flush()

        with transaction.atomic():
            packages = self.make_packages()
            pops = self.make_pops()
            routers = self.make_routers(pops)
            onus = self.make_onus(len(pops) * 40)
            self.make_staff()
            self.make_stock()
            subscribers = self.make_subscribers(
                options['subscribers'], packages, routers, pops, onus)
            self.make_tasks(60)
            self.make_ledger()
            self.make_events(subscribers)

        self.report()

    # ------------------------------------------------------------------
    def flush(self):
        self.stdout.write('Clearing existing data...')
        ServiceEvent.objects.all().delete()
        Subscriber.objects.all().delete()
        Tasks.objects.all().delete()
        TaskCategory.objects.all().delete()
        Warehouse.objects.all().delete()
        WarehouseCategory.objects.all().delete()
        Onu.objects.all().delete()
        Employ.objects.all().delete()
        EmployCategory.objects.all().delete()
        Invest.objects.all().delete()
        Earning.objects.all().delete()
        Package.objects.all().delete()
        Router.objects.all().delete()
        Pop.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    def make_packages(self):
        specs = [
            ('Starter 5M', 5000, 2500, '600', 30),
            ('Home 10M', 10000, 5000, '1000', 30),
            ('Home 15M', 15000, 7500, '1400', 30),
            ('Home 20M', 20000, 10000, '1800', 30),
            ('Home 30M', 30000, 15000, '2500', 30),
            ('Business 50M', 50000, 50000, '5000', 30),
            ('Business 100M', 100000, 100000, '9000', 30),
        ]
        packages = []
        for name, down, up, price, cycle in specs:
            pkg, _ = Package.objects.get_or_create(
                name=name,
                defaults={
                    'download_kbps': down, 'upload_kbps': up,
                    'price': Decimal(price), 'billing_cycle_days': cycle,
                },
            )
            packages.append(pkg)
        return packages

    def make_pops(self):
        core, _ = Pop.objects.get_or_create(
            name='Uttara Core', defaults={'input_power': -12})
        pops = [core]
        for name, power in [('Mirpur POP 1', -15), ('Mirpur POP 2', -17),
                            ('Dhanmondi POP', -14), ('Savar Edge', -19),
                            ('Badda POP', -16)]:
            pop, _ = Pop.objects.get_or_create(
                name=name, defaults={'main_pop': core, 'input_power': power})
            pops.append(pop)
        return pops

    def make_routers(self, pops):
        specs = [
            ('Uttara-Core', '10.10.0.1', True, Router.Status.REACHABLE, False),
            ('Mirpur-POP-1', '10.10.2.1', True, Router.Status.REACHABLE, False),
            ('Mirpur-POP-2', '10.10.2.2', False, Router.Status.UNREACHABLE, False),
            ('Dhanmondi-Edge', '10.10.3.1', True, Router.Status.REACHABLE, False),
            ('Savar-Edge', '10.10.4.1', False, Router.Status.REACHABLE, True),
            ('Badda-Edge', '10.10.5.1', True, Router.Status.AUTH_FAILED, False),
        ]
        routers = []
        for i, (name, host, tls, status, dry) in enumerate(specs):
            router, created = Router.objects.get_or_create(
                name=name,
                defaults={
                    'host': host,
                    'api_port': 8729 if tls else 8728,
                    'use_tls': tls,
                    'username': 'ispms-api',
                    'pop': pops[i % len(pops)],
                    'status': status,
                    'dry_run': dry,
                    'routeros_version': random.choice(['7.14.3', '7.15.2', '6.49.10']),
                    'board_name': random.choice(['CCR2004-1G-12S+2XS', 'hEX S', 'RB4011']),
                    'last_seen': timezone.now() - timedelta(
                        minutes=0 if status == Router.Status.REACHABLE else 14),
                },
            )
            if created and settings.ROUTER_CRED_KEY:
                router.set_password(f'demo-pw-{i}')
                router.save(update_fields=['password_enc'])
            routers.append(router)
        return routers

    def make_onus(self, count):
        existing = Onu.objects.count()
        onus = list(Onu.objects.all())
        for i in range(existing, count):
            brand, model = random.choice(ONU_BRANDS)
            onus.append(Onu(
                brand=brand, model=model,
                mac=':'.join(f'{random.randint(0, 255):02X}' for _ in range(6)),
                port=random.randint(1, 16),
                status=random.choices(['Active', 'Stored', 'Damaged'],
                                      weights=[85, 10, 5])[0],
            ))
        Onu.objects.bulk_create([o for o in onus if o.pk is None])
        return list(Onu.objects.all())

    def make_staff(self):
        categories = {}
        for name in ['Technician', 'Line Man', 'Collector', 'Support', 'Manager']:
            categories[name], _ = EmployCategory.objects.get_or_create(name=name)

        for i in range(18):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            email = f'staff{i}@demo.isp'
            if Employ.objects.filter(email=email).exists():
                continue
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={'first_name': first, 'last_name': last, 'is_active': True},
            )
            Employ.objects.create(
                user=user, name=f'{first} {last}',
                father_name=f'{random.choice(FIRST_NAMES)} {last}',
                mother_name=f'{random.choice(FIRST_NAMES)} {last}',
                email=email, phone=f'018{random.randint(10000000, 99999999)}',
                nid=str(random.randint(1000000000, 9999999999)),
                address=random.choice(AREAS),
                status=random.choices(['active', 'inactive'], weights=[90, 10])[0],
                type=random.choice(list(categories.values())),
            )

    def make_stock(self):
        categories = {}
        for name in ['Router', 'Switch', 'ONU', 'Cable', 'Power']:
            categories[name], _ = WarehouseCategory.objects.get_or_create(name=name)

        existing = Warehouse.objects.count()
        items = []
        for i in range(existing, 70):
            brand, model = random.choice(STOCK)
            items.append(Warehouse(
                Brand=brand, model=model,
                serial=f'SN{random.randint(100000, 999999)}',
                category=random.choice(list(categories.values())),
                status=random.choices(['Active', 'Stored', 'Damaged'],
                                      weights=[60, 33, 7])[0],
            ))
        Warehouse.objects.bulk_create(items)

    def make_subscribers(self, count, packages, routers, pops, onus):
        now = timezone.now()
        existing = Subscriber.objects.count()
        start_account = 2000 + existing

        subscribers = []
        used_ips = set(Subscriber.objects.exclude(static_ip=None)
                       .values_list('static_ip', flat=True))
        used_names = set(Subscriber.objects.exclude(pppoe_username=None)
                         .values_list('pppoe_username', flat=True))

        for i in range(count):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            account = str(start_account + i)

            # 80% PPPoE, 20% static — roughly what a small ISP looks like
            is_pppoe = random.random() < 0.8

            username = None
            static_ip = None
            if is_pppoe:
                base = f'{first.lower()}.{last.lower()}{i}'
                username = base
                while username in used_names:
                    username = f'{base}{random.randint(1, 999)}'
                used_names.add(username)
            else:
                ip = f'10.{random.randint(40, 60)}.{random.randint(0, 255)}.{random.randint(2, 254)}'
                while ip in used_ips:
                    ip = f'10.{random.randint(40, 60)}.{random.randint(0, 255)}.{random.randint(2, 254)}'
                used_ips.add(ip)
                static_ip = ip

            # weighted so the list has something worth looking at
            state = random.choices(
                [Subscriber.State.ACTIVE, Subscriber.State.GRACE,
                 Subscriber.State.SUSPENDED, Subscriber.State.PENDING,
                 Subscriber.State.TERMINATED],
                weights=[74, 8, 12, 4, 2],
            )[0]

            if state == Subscriber.State.ACTIVE:
                expires = now + timedelta(days=random.randint(1, 29))
            elif state == Subscriber.State.GRACE:
                expires = now - timedelta(days=random.randint(1, 3))
            elif state == Subscriber.State.SUSPENDED:
                expires = now - timedelta(days=random.randint(4, 60))
            else:
                expires = None

            sub = Subscriber(
                account_no=account,
                name=f'{first} {last}',
                email=f'{first.lower()}{i}@example.com' if random.random() < 0.6 else '',
                phone=f'017{random.randint(10000000, 99999999)}',
                nid=str(random.randint(1000000000, 9999999999)),
                address=random.choice(AREAS),
                connection_type=(Subscriber.Connection.PPPOE if is_pppoe
                                 else Subscriber.Connection.STATIC_IP),
                pppoe_username=username,
                static_ip=static_ip,
                mac_address=('' if is_pppoe else
                             ':'.join(f'{random.randint(0, 255):02X}' for _ in range(6))),
                router=random.choice(routers),
                package=random.choices(packages, weights=[10, 30, 20, 20, 12, 5, 3])[0],
                pop=random.choice(pops),
                onu=random.choice(onus) if onus and random.random() < 0.7 else None,
                service_state=state,
                expires_at=expires,
                grace_days=random.choice([3, 3, 3, 5, 7]),
                sync_state=random.choices(
                    [Subscriber.Sync.SYNCED, Subscriber.Sync.PENDING,
                     Subscriber.Sync.DRIFTED, Subscriber.Sync.FAILED],
                    weights=[85, 7, 5, 3])[0],
            )
            if is_pppoe:
                sub.set_pppoe_password(generate_pppoe_password())
            subscribers.append(sub)

        Subscriber.objects.bulk_create(subscribers, batch_size=200)
        return list(Subscriber.objects.all())

    def make_tasks(self, count):
        categories = {}
        for name in ['Installation', 'Fault', 'Maintenance', 'Shifting', 'Complaint']:
            categories[name], _ = TaskCategory.objects.get_or_create(name=name)

        staff = list(Employ.objects.all())
        if not staff:
            return

        existing = Tasks.objects.count()
        for i in range(existing, count):
            Tasks.objects.create(
                title=random.choice(TASK_TITLES),
                task_category=random.choice(list(categories.values())),
                describe='Reported by customer. Field visit required.',
                equipment_price=random.choice([0, 0, 350, 800, 1200]),
                client_charged=random.choice([0, 0, 500, 1000]),
                traveling_allowance=random.choice([0, 100, 150, 200]),
                creator=random.choice(staff),
                solver=random.choice(staff) if random.random() < 0.8 else None,
                task_token=1000 + i,
                status=random.choices(['pending', 'in progress', 'complete'],
                                      weights=[25, 20, 55])[0],
                approved=random.random() < 0.7,
            )

    def make_ledger(self):
        if Invest.objects.exists():
            return
        for details, amount in [
            ('Fiber cable purchase — 2km', 145000),
            ('MikroTik CCR2004 for Uttara core', 98000),
            ('Splitter and connector stock', 32000),
            ('Generator for Mirpur POP', 76000),
            ('Vehicle maintenance', 18000),
        ]:
            Invest.objects.create(invest_details=details, invest_amount=amount)

        for details, amount in [
            ('Monthly subscriber collection — June', 512000),
            ('Monthly subscriber collection — July', 548000),
            ('New connection fees', 84000),
            ('Equipment sale to customers', 26000),
        ]:
            Earning.objects.create(earning_details=details, earning_amount=amount)

    def make_events(self, subscribers):
        """A few subscribers get a real history so the timeline has content."""
        if ServiceEvent.objects.count() > 20:
            return

        actor = User.objects.filter(is_superuser=True).first()
        sample = random.sample(subscribers, min(40, len(subscribers)))

        for sub in sample:
            record_event(subject=sub, action='created', actor=actor,
                         reason='account opened')
            record_event(subject=sub, action='state_change', actor=actor,
                         state_before='pending', state_after='active',
                         reason='first payment received')
            if sub.service_state in (Subscriber.State.GRACE,
                                     Subscriber.State.SUSPENDED):
                record_event(subject=sub, action='state_change',
                             state_before='active', state_after='grace',
                             reason='expired')
            if sub.service_state == Subscriber.State.SUSPENDED:
                record_event(subject=sub, action='state_change',
                             state_before='grace', state_after='suspended',
                             reason='grace_elapsed')
                record_event(subject=sub, action='provision',
                             reason='secret disabled, session dropped',
                             payload={'router': sub.router.name, 'took_ms': 1180})

    def report(self):
        self.stdout.write('')
        for label, model in [
            ('Subscribers', Subscriber), ('Packages', Package), ('Routers', Router),
            ('POPs', Pop), ('ONUs', Onu), ('Tasks', Tasks),
            ('Warehouse items', Warehouse), ('Employees', Employ),
            ('Service events', ServiceEvent),
        ]:
            self.stdout.write(f'  {label:18} {model.objects.count():5d}')

        self.stdout.write('')
        for state, _ in Subscriber.State.choices:
            count = Subscriber.objects.filter(service_state=state).count()
            self.stdout.write(f'  {state:18} {count:5d}')

        self.stdout.write(self.style.SUCCESS('\nDemo data ready.'))
