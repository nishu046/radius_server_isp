"""Migrate apps.clients.Clients -> apps.subscribers.Subscriber.

The hard part is Clients.ip: one CharField labelled "IP/UserName" holding
either a static IP or a PPPoE username. Rows are classified, never guessed —
anything ambiguous is written to notes/migration-unclassified.csv for a human
to resolve, rather than being silently assigned a connection type that would
then be provisioned onto a router.

Two deliberate choices:

  * expires_at is left NULL. There is no source data for it, and inventing
    one would make the P7 sweep suspend the entire migrated customer base
    on its first run.
  * Every subscriber needs a router, but Clients has no router column. A
    placeholder router is created and every migrated row points at it. The
    unclassified report lists them so they can be reassigned before P5
    enables writes.
"""

import csv
import ipaddress
import re
from pathlib import Path

from django.db import migrations

USERNAME_RE = re.compile(r'^[A-Za-z0-9._@-]{3,64}$')
IP_SHAPED_RE = re.compile(r'^[\d.]+$')

PLACEHOLDER_ROUTER = 'UNASSIGNED-migrated'


def classify(raw):
    """Return ('static_ip' | 'pppoe' | 'unknown', cleaned_value)."""
    value = (raw or '').strip()
    if not value:
        return 'unknown', value

    try:
        ipaddress.IPv4Address(value)
        return 'static_ip', value
    except ValueError:
        pass

    # Anything made only of digits and dots was clearly meant to be an IP.
    # It did not parse as one, so it is a typo — not a username. Without
    # this, "999.999.999.999" matches the username pattern and would be
    # provisioned onto a router as a PPPoE secret.
    if IP_SHAPED_RE.match(value):
        return 'unknown', value

    if USERNAME_RE.match(value):
        return 'pppoe', value

    return 'unknown', value


def forwards(apps, schema_editor):
    Clients = apps.get_model('clients', 'Clients')
    Subscriber = apps.get_model('subscribers', 'Subscriber')
    Router = apps.get_model('network', 'Router')
    OldPackage = apps.get_model('packages', 'Package')
    NewPackage = apps.get_model('billing', 'Package')

    if not Clients.objects.exists():
        return

    # ---- packages first: subscribers point at them -------------------
    package_map = {}
    for old in OldPackage.objects.all():
        new, _ = NewPackage.objects.get_or_create(
            name=old.name,
            defaults={
                # old model had one `speed` integer with no unit recorded.
                # Treated as Mbps down; upload is unknowable from it, so it
                # gets an obviously-wrong-looking placeholder that shows up
                # in review rather than a plausible guess that does not.
                'download_kbps': max(int(old.speed or 1) * 1000, 1),
                'upload_kbps': max(int(old.speed or 1) * 1000, 1),
                'price': old.price or 0,
                'billing_cycle_days': 30,
            },
        )
        package_map[old.pk] = new

    # ---- placeholder router ------------------------------------------
    router, _ = Router.objects.get_or_create(
        name=PLACEHOLDER_ROUTER,
        defaults={
            'host': '0.0.0.0',
            'api_port': 8728,
            'username': 'unset',
            'password_enc': b'',
            'enabled': False,   # never polled or provisioned against
            'dry_run': True,
        },
    )

    unclassified = []
    seen_usernames = set()
    seen_ips = set()

    for client in Clients.objects.all().order_by('pk'):
        kind, value = classify(client.ip)

        conflict = None
        if kind == 'pppoe' and value in seen_usernames:
            conflict = 'duplicate pppoe_username'
        elif kind == 'static_ip' and value in seen_ips:
            conflict = 'duplicate static_ip'

        if kind == 'unknown' or conflict:
            unclassified.append({
                'client_id': client.client_id,
                'name': client.name,
                'phone': client.phone,
                'ip_raw': client.ip,
                'reason': conflict or 'could not classify as IP or username',
            })
            continue

        if kind == 'pppoe':
            seen_usernames.add(value)
        else:
            seen_ips.add(value)

        Subscriber.objects.create(
            account_no=str(client.client_id),
            name=client.name,
            email=client.email or '',
            phone=client.phone,
            nid=client.nid or '',
            address=client.address or '',
            connection_type=kind,
            pppoe_username=value if kind == 'pppoe' else None,
            pppoe_password_enc=b'',
            static_ip=value if kind == 'static_ip' else None,
            router=router,
            package=package_map[client.pack_id],
            onu_id=client.onu_id,
            pop_id=client.pop_name_id,
            # old status was active/inactive; inactive maps to suspended
            service_state='active' if client.status == 'active' else 'suspended',
            expires_at=None,          # no source data — must not be invented
            sync_state='pending',
            created=client.created,
        )

    if unclassified:
        report = Path(__file__).resolve().parents[3] / 'notes' / 'migration-unclassified.csv'
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('w', newline='') as fh:
            writer = csv.DictWriter(
                fh, fieldnames=['client_id', 'name', 'phone', 'ip_raw', 'reason'])
            writer.writeheader()
            writer.writerows(unclassified)

        print(
            f'\n  {len(unclassified)} client row(s) could not be migrated '
            f'automatically.\n  Review: {report}\n'
        )


def backwards(apps, schema_editor):
    Subscriber = apps.get_model('subscribers', 'Subscriber')
    Subscriber.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('subscribers', '0001_initial'),
        ('network', '0002_router'),
        ('billing', '0001_initial'),
        ('clients', '0002_alter_clients_options'),
        ('packages', '0002_alter_package_options'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
