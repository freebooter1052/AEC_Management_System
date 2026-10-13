import getpass

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from apps.accounts import users
from apps.accounts.serializers import validate_password_strength
from apps.core import audit, repository
from apps.core.roles import ADMIN


class Command(BaseCommand):
    help = "Create an administrator account (user document with role=admin)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="System Administrator")
        parser.add_argument("--password", help="Omit to be prompted (recommended).")

    def handle(self, *args, email, name, password, **options):
        if users.email_taken(email):
            raise CommandError(f"An account with email {email} already exists.")
        if not password:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("Passwords do not match.")
        try:
            validate_password_strength(password)
        except ValidationError as exc:
            raise CommandError(" ".join(str(d) for d in exc.detail)) from exc

        user = users.build_user(email=email, password=password, role=ADMIN, full_name=name)
        repository.save(user)
        audit.record("auth.admin_created", target_id=user["_id"], details={"via": "manage.py create_admin"})
        self.stdout.write(self.style.SUCCESS(f"Administrator {user['email']} created ({user['_id']})."))
