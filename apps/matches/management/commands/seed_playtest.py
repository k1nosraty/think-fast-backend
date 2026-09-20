import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.accounts.models import GuestIdentity
from apps.matches.rooms import create_room, join_room, set_ready, start_room


class Command(BaseCommand):
    help = "Create a ready-to-play private 1v1 room and print one-time guest tokens."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--preset", default="number_classic_5_v1")

    def handle(self, *args: object, **options: Any) -> None:
        host, host_token = GuestIdentity.issue(display_name="PlaytestHost", avatar_id="avatar_01")
        opponent, opponent_token = GuestIdentity.issue(
            display_name="PlaytestGuest", avatar_id="avatar_02"
        )
        room, _ = create_room(guest=host, command_id=uuid.uuid4(), preset_id=str(options["preset"]))
        join_room(guest=opponent, room_id=room.id, command_id=uuid.uuid4())
        set_ready(guest=host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=opponent, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        match, _ = start_room(guest=host, room_id=room.id, command_id=uuid.uuid4())
        self.stdout.write(
            self.style.SUCCESS(
                "\n".join(
                    [
                        f"room_id={room.id}",
                        f"join_code={room.join_code}",
                        f"match_id={match.id}",
                        f"host_token={host_token}",
                        f"opponent_token={opponent_token}",
                    ]
                )
            )
        )
