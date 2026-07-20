from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import PackageForm
from .models import Package


class PackageListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'billing.view_package'
    model = Package
    template_name = 'billing/package_list.html'
    context_object_name = 'packages'
    paginate_by = 25

    def get_queryset(self):
        # subscriber counts drive the "in use" column, and a package in use
        # cannot be deleted (PROTECT), so the count explains why
        #
        # order_by is explicit because annotate() sets group_by, and Django
        # reports a grouped queryset as unordered regardless of Meta.ordering
        # — which brings back the pagination bug P0 fixed.
        return super().get_queryset().annotate(
            subscriber_count=Count('subscribers'),
            active_count=Count('subscribers',
                               filter=Q(subscribers__service_state='active')),
        ).order_by('download_kbps', 'name', 'id')


class PackageCreateView(LoginRequiredMixin, PermissionRequiredMixin,
                        SuccessMessageMixin, CreateView):
    permission_required = 'billing.add_package'
    model = Package
    form_class = PackageForm
    template_name = 'billing/package_form.html'
    success_url = reverse_lazy('billing:packages')
    success_message = 'Package "%(name)s" created'


class PackageUpdateView(LoginRequiredMixin, PermissionRequiredMixin,
                        SuccessMessageMixin, UpdateView):
    permission_required = 'billing.change_package'
    model = Package
    form_class = PackageForm
    template_name = 'billing/package_form.html'
    success_url = reverse_lazy('billing:packages')
    success_message = 'Package "%(name)s" updated'


class PackageDeleteView(LoginRequiredMixin, PermissionRequiredMixin,
                        SuccessMessageMixin, DeleteView):
    permission_required = 'billing.delete_package'
    model = Package
    template_name = 'billing/package_confirm_delete.html'
    success_url = reverse_lazy('billing:packages')
    success_message = 'Package deleted'
