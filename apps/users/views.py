# imports
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView, View

from .decorator import anonymous_only
from .forms import RegisterForm, UserUpdateForm
from .models import Profile

'''
User Model

'''
User = get_user_model()


class UsersView(LoginRequiredMixin, PermissionRequiredMixin, View):
    login_url = 'login'
    permission_required = 'users.view_user'

    def get(self, request):
        users = User.objects.all().prefetch_related('groups')
        return render(request, 'auth/users.html', {'users': users})


'''
Create User

'''
@login_required(login_url='login')
@permission_required('users.add_user', raise_exception=True)
def register(request):
    form = RegisterForm()
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'User created')
            return redirect('user')
    return render(request, 'auth/createUser.html', {'form': form})


'''
Update User

'''
class UpdateUser(LoginRequiredMixin, PermissionRequiredMixin,
                 SuccessMessageMixin, UpdateView):
    login_url = 'login'
    permission_required = 'users.change_user'
    model = User
    template_name = 'auth/user_form.html'
    form_class = UserUpdateForm
    success_url = '/users'
    success_message = 'User updated successfully'


'''
Delete User

'''
@login_required(login_url='login')
@permission_required('users.delete_user', raise_exception=True)
@require_POST
def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)

    if user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user')

    user.delete()
    messages.success(request, 'User deleted')
    return redirect('user')


'''
login user

'''
@anonymous_only
def loginView(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            if 'next' in request.POST:
                return redirect(request.POST['next'])
            return redirect('dashboard:dashboard')

        messages.error(request, 'Email or password is incorrect.')
    return render(request, 'auth/login.html')


'''
log out user

'''
@require_POST
def logoutView(request):
    logout(request)
    return redirect('/')


'''
profile view

'''
class ProfileView(LoginRequiredMixin, View):
    login_url = 'login'

    def get(self, request):
        profile, _ = Profile.objects.get_or_create(
            user=request.user,
            defaults={
                'name': request.user.get_full_name(),
                'gender': request.user.gender or '',
            },
        )
        return render(request, 'users/profile.html', {'user_data': profile})
