from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.network.models import ServiceEvent

from .filters import SubscriberFilter
from .forms import SubscriberForm
from .models import Subscriber
from .services import InvalidTransition, transition


class SubscriberListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'subscribers.view_subscriber'
    model = Subscriber
    template_name = 'subscribers/subscriber_list.html'
    context_object_name = 'subscribers'
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            super().get_queryset()
            .select_related('package', 'router', 'pop')
            .order_by('-created', '-id')
        )
        self.filterset = SubscriberFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset

        counts = Subscriber.objects.aggregate(
            active=Count('pk', filter=Q(service_state=Subscriber.State.ACTIVE)),
            grace=Count('pk', filter=Q(service_state=Subscriber.State.GRACE)),
            suspended=Count('pk', filter=Q(service_state=Subscriber.State.SUSPENDED)),
            drifted=Count('pk', filter=Q(sync_state=Subscriber.Sync.DRIFTED)),
        )
        context['counts'] = counts
        return context


class SubscriberDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'subscribers.view_subscriber'
    model = Subscriber
    template_name = 'subscribers/subscriber_detail.html'
    context_object_name = 'subscriber'

    def get_queryset(self):
        return super().get_queryset().select_related('package', 'router', 'pop', 'onu')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # the timeline merges billing, state changes and router operations
        # into one record — this is the screen opened when a customer
        # disputes a disconnection
        context['events'] = ServiceEvent.objects.for_subject(self.object)[:50]
        return context


class SubscriberCreateView(LoginRequiredMixin, PermissionRequiredMixin,
                           SuccessMessageMixin, CreateView):
    permission_required = 'subscribers.add_subscriber'
    model = Subscriber
    form_class = SubscriberForm
    template_name = 'subscribers/subscriber_form.html'
    success_message = 'Subscriber "%(name)s" created'

    def get_success_url(self):
        return reverse('subscribers:detail', args=[self.object.pk])


class SubscriberUpdateView(LoginRequiredMixin, PermissionRequiredMixin,
                           SuccessMessageMixin, UpdateView):
    permission_required = 'subscribers.change_subscriber'
    model = Subscriber
    form_class = SubscriberForm
    template_name = 'subscribers/subscriber_form.html'
    success_message = 'Subscriber "%(name)s" updated'

    def get_success_url(self):
        return reverse('subscribers:detail', args=[self.object.pk])


class SubscriberDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = 'subscribers.delete_subscriber'
    model = Subscriber
    template_name = 'subscribers/subscriber_confirm_delete.html'
    success_url = reverse_lazy('subscribers:list')


@require_POST
def change_state(request, pk, to_state):
    """Manual state override.

    Requires change_subscriber — deliberately not the same permission as
    recording a payment, because suspending someone is a different level
    of trust from taking their money.
    """
    if not request.user.has_perm('subscribers.change_subscriber'):
        messages.error(request, 'You do not have permission to change service state.')
        return redirect('subscribers:detail', pk=pk)

    subscriber = get_object_or_404(Subscriber, pk=pk)
    reason = request.POST.get('reason', '').strip() or 'manual override'

    try:
        transition(subscriber, to_state, reason=reason, actor=request.user)
    except InvalidTransition as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'{subscriber.name} is now {to_state}.')

    return redirect('subscribers:detail', pk=pk)
