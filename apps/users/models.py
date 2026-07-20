# imports
import os

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


# role group names — created and populated in apps.users.roles
ROLE_OWNER = 'owner'
ROLE_MANAGER = 'manager'
ROLE_COLLECTOR = 'collector'
ROLE_TECHNICIAN = 'technician'


# user manager
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('Enter a valid email')

        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_staffuser(self, email, password=None, **extra):
        extra.setdefault('is_staff', True)
        return self.create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)

        if extra.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')

        return self.create_user(email, password, **extra)


# user model
class User(AbstractBaseUser, PermissionsMixin):
    """Authorization comes from PermissionsMixin — groups and permissions.

    The previous implementation overrode has_perm() and has_module_perms() to
    return True unconditionally, which made every authenticated account a full
    administrator. Those overrides are gone; do not reintroduce them.
    """

    email = models.EmailField(max_length=245, unique=True)
    first_name = models.CharField(max_length=245, blank=True)
    last_name = models.CharField(max_length=245, blank=True)
    gender = models.CharField(max_length=245, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text='Can sign in to the Django admin.',
    )
    # is_superuser is supplied by PermissionsMixin

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # username replaced with email
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ['email']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    def get_short_name(self):
        return self.first_name or self.email

    # convenience role checks — these gate UI affordances, never access itself.
    # access decisions must go through permissions so they stay auditable.
    def in_role(self, *names):
        return self.groups.filter(name__in=names).exists()

    @property
    def is_owner(self):
        return self.is_superuser or self.in_role(ROLE_OWNER)


# img rename
def img_uploader(instance, filename):
    return os.path.join('profiles_img', instance.user.email, filename)


# Profile Model
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=245)
    gender = models.CharField(max_length=10)
    img = models.ImageField(upload_to=img_uploader, null=True, blank=True)
    bio = models.CharField(max_length=245, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Profile'
        verbose_name_plural = 'Profiles'
        ordering = ['-id']
