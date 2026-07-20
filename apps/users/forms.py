# imports
from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.models import Group

User = get_user_model()


class _PasswordPairMixin:
    """Shared confirm-password handling.

    Runs Django's configured password validators, which the previous
    implementation skipped entirely — AUTH_PASSWORD_VALIDATORS was configured
    but never actually applied to any user-facing form.
    """

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Your passwords must match')
            return cleaned_data

        if password1:
            try:
                password_validation.validate_password(password1, self.instance)
            except forms.ValidationError as exc:
                self.add_error('password', exc)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
            self.save_m2m()
        return user


# user register form
class RegisterForm(_PasswordPairMixin, forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())
    password2 = forms.CharField(
        widget=forms.PasswordInput(), label='Confirm Password')
    roles = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Determines what this user can see and do.',
    )

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'gender']

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            user.groups.set(self.cleaned_data.get('roles') or [])
        return user


# superuser create form
class UserAdminCreationForm(_PasswordPairMixin, forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())
    password2 = forms.CharField(
        widget=forms.PasswordInput(), label='Confirm Password')

    class Meta:
        model = User
        fields = ['email']


# user admin change form
class UserAdminChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = ['email', 'password', 'is_active', 'is_staff', 'is_superuser', 'groups']

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        return self.initial['password']


# user update form
class UserUpdateForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Determines what this user can see and do.',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['roles'].initial = self.instance.groups.all()

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            user.groups.set(self.cleaned_data.get('roles') or [])
        return user
