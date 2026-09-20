from django.core.management.base import BaseCommand

from apps.accounts.models import GuestIdentity
from apps.matches.services import create_solo


class Command(BaseCommand):
    help = "Create one local guest and active Solo match; prints the one-time token."

    def handle(self, *args: object, **options: object) -> None:
        guest, token = GuestIdentity.issue(display_name="DemoPlayer", avatar_id="avatar_01")
        import uuid

        match, _ = create_solo(
            guest=guest, command_id=uuid.uuid4(), preset_id="number_classic_5_v1"
        )
        self.stdout.write(
            self.style.SUCCESS(f"guest_id={guest.id}\naccess_token={token}\nmatch_id={match.id}")
        )
