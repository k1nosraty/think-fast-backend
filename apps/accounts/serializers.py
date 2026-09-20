from rest_framework import serializers


class CreateGuestSerializer(serializers.Serializer[dict[str, str]]):
    display_name = serializers.CharField(min_length=3, max_length=20, trim_whitespace=True)
    avatar_id = serializers.RegexField(r"^avatar_[0-9]{2}$", max_length=50)
