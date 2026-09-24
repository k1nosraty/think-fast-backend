from rest_framework import serializers

from apps.games.domain import CREATABLE_PRESET_IDS
from apps.matches.models import Room


class CreateSoloSerializer(serializers.Serializer[dict[str, object]]):
    command_id = serializers.UUIDField()
    # Gated presets (Word) are intentionally absent; see `CREATABLE_PRESET_IDS`.
    preset_id = serializers.ChoiceField(choices=list(CREATABLE_PRESET_IDS))


class CreateRoomSerializer(CreateSoloSerializer):
    challenge_source = serializers.ChoiceField(
        choices=Room.ChallengeSource.values, default=Room.ChallengeSource.SYSTEM
    )
    room_mode = serializers.ChoiceField(choices=Room.Mode.values, default=Room.Mode.DUEL)
    rounds_count = serializers.IntegerField(min_value=1, max_value=15, default=Room.DEFAULT_ROUNDS)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        # FT-04: the documented Party round set (3/5/7) is enforced at the API
        # boundary, not just in the UI. Duel ignores the field (always 1 round).
        if attrs.get("room_mode") == Room.Mode.PARTY and attrs.get(
            "rounds_count"
        ) not in Room.allowed_rounds(Room.Mode.PARTY):
            raise serializers.ValidationError(
                {"rounds_count": "Party rooms allow 3, 5 or 7 rounds."}
            )
        return attrs


class GuessSerializer(serializers.Serializer[dict[str, object]]):
    command_id = serializers.UUIDField()
    guess = serializers.JSONField()


class CommandSerializer(serializers.Serializer[dict[str, object]]):
    command_id = serializers.UUIDField()


class ReadySerializer(CommandSerializer):
    ready = serializers.BooleanField()


class KickMemberSerializer(CommandSerializer):
    target_participant_id = serializers.UUIDField()


class UpdateRoomRulesSerializer(serializers.Serializer[dict[str, object]]):
    # Same gated allowlist as creation: a Room must not be switched to a preset
    # that cannot be instantiated.
    preset_id = serializers.ChoiceField(choices=list(CREATABLE_PRESET_IDS))


class RematchSerializer(CommandSerializer):
    action = serializers.ChoiceField(choices=["request", "decline"], default="request")


class CommitChallengeSerializer(CommandSerializer):
    secret = serializers.JSONField()
