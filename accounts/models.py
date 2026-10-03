from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Email is the login, so the default username-based manager cannot be used."""

    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra):
        if not email:
            raise ValueError("An email address is required")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("A superuser must have is_staff and is_superuser set")
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email
