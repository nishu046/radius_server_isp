from django import forms

from apps.core.forms import TailwindModelForm

from .models import Package


class PackageForm(TailwindModelForm):
    class Meta:
        model = Package
        fields = [
            'name',
            'download_kbps', 'upload_kbps',
            'burst_download_kbps', 'burst_upload_kbps',
            'price', 'billing_cycle_days', 'is_active',
        ]
        labels = {
            'download_kbps': 'Download (kbps)',
            'upload_kbps': 'Upload (kbps)',
            'burst_download_kbps': 'Burst download (kbps)',
            'burst_upload_kbps': 'Burst upload (kbps)',
            'billing_cycle_days': 'Billing cycle (days)',
        }
        help_texts = {
            'download_kbps': 'What the subscriber downloads at.',
            'upload_kbps': 'What the subscriber uploads at.',
            'billing_cycle_days': 'Days of service one payment buys.',
        }

    def clean(self):
        cleaned = super().clean()
        down = cleaned.get('download_kbps')
        up = cleaned.get('upload_kbps')

        # Not an error — asymmetric-upstream plans are legitimate — but on a
        # residential ISP an upload above download is nearly always the
        # rate-limit direction being entered backwards.
        if down and up and up > down:
            self.add_error(
                'upload_kbps',
                'Upload is higher than download. Check these are not reversed — '
                'RouterOS writes rate limits as upload/download.',
            )

        for burst, base in (('burst_download_kbps', 'download_kbps'),
                            ('burst_upload_kbps', 'upload_kbps')):
            burst_value = cleaned.get(burst)
            base_value = cleaned.get(base)
            if burst_value and base_value and burst_value < base_value:
                self.add_error(burst, 'Burst cannot be lower than the base rate.')

        return cleaned
