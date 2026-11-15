from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import LawyerProfile


class Command(BaseCommand):
    help = "Create demo accounts; preserve existing accounts unless passwords are reset explicitly."

    def add_arguments(self, parser):
        parser.add_argument("--reset-passwords", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        accounts = [
            ("demo_anya", "user", settings.DEMO_USER_PASSWORD),
            ("demo_lawyer_1", "lawyer", settings.DEMO_LAWYER_PASSWORD),
            ("demo_lawyer_2", "lawyer", settings.DEMO_LAWYER_PASSWORD),
            ("demo_moderator", "moderator", settings.DEMO_MODERATOR_PASSWORD),
            ("demo_editor", "editor", settings.DEMO_EDITOR_PASSWORD),
        ]
        for username, role, password in accounts:
            user, created = user_model.objects.get_or_create(
                username=username,
                defaults={"role": role, "is_demo": True, "is_staff": role == "moderator"},
            )
            if not user.is_demo:
                raise CommandError("Demo username is occupied by a non-demo account.")
            if created or options["reset_passwords"]:
                user.set_password(password)
                user.save(update_fields=["password"])
            if created and role == "lawyer":
                LawyerProfile.objects.get_or_create(user=user)
        self.stdout.write(
            self.style.SUCCESS("Demo accounts are ready. Passwords were not printed.")
        )
