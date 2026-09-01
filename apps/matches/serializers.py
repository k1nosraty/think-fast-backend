from rest_framework import serializers

from apps.games.domain import PRESETS


class CreateSoloSerializer(serializers.Serializer[dict[str, object]]):
    command_id = serializers.UUIDField()
    preset_id = serializers.ChoiceField(choices=list(PRESETS))


class CreateRoomSerializer(CreateSoloSerializer):
    challenge_source = serializers.ChoiceField(choices=["system", "players"], default="system")


class GuessSerializer(serializers.Serializer[dict[str, object]]):
    command_id = serializers.UUIDField()
    guess = serializers.JSONField()


class CommandSerializer(serializers.Serializer[dict[str, object]]):
    command_id = serializers.UUIDField()


class ReadySerializer(CommandSerializer):
    ready = serializers.BooleanField()


class KickMemberSerializer(serializers.Serializer[dict[str, object]]):
    target_participant_id = serializers.UUIDField()


class UpdateRoomRulesSerializer(serializers.Serializer[dict[str, object]]):
    preset_id = serializers.ChoiceField(choices=list(PRESETS))


class RematchSerializer(CommandSerializer):
    action = serializers.ChoiceField(choices=["request", "decline"], default="request")


class CommitChallengeSerializer(CommandSerializer):
    secret = serializers.JSONField()
