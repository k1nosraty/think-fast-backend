import uuid

from django.db import models

from apps.accounts.models import GuestIdentity


class Match(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active"
        FINISHED = "finished"
        ABANDONED = "abandoned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state = models.CharField(max_length=20, choices=State, default=State.ACTIVE)
    rules = models.JSONField()
    started_at = models.DateTimeField()
    deadline = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    latest_sequence = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class Participant(models.Model):
    class SolveState(models.TextChoices):
        PLAYING = "playing"
        SOLVED = "solved"
        UNSOLVED = "unsolved"
        ABANDONED = "abandoned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="participants")
    guest = models.ForeignKey(
        GuestIdentity, on_delete=models.PROTECT, related_name="participations"
    )
    display_name = models.CharField(max_length=20)
    avatar_id = models.CharField(max_length=50)
    attempt_count = models.PositiveIntegerField(default=0)
    solve_state = models.CharField(max_length=20, choices=SolveState, default=SolveState.PLAYING)
    solved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["match", "guest"], name="unique_match_guest")
        ]


class Challenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name="challenge")
    protected_secret = models.TextField(editable=False)


class Attempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="attempts")
    command_id = models.UUIDField()
    request_fingerprint = models.CharField(max_length=64)
    ordinal = models.PositiveIntegerField()
    guess = models.CharField(max_length=6)
    feedback = models.JSONField()
    solved = models.BooleanField(default=False)
    accepted_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "command_id"], name="unique_participant_command"
            ),
            models.UniqueConstraint(
                fields=["participant", "ordinal"], name="unique_participant_ordinal"
            ),
        ]
        ordering = ["ordinal"]


class Result(models.Model):
    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, primary_key=True, related_name="result"
    )
    outcome = models.CharField(max_length=20)
    reason = models.CharField(max_length=20)
    winner_participant_ids = models.JSONField(default=list)
    secret_revealed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class CommandRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guest = models.ForeignKey(GuestIdentity, on_delete=models.CASCADE, related_name="commands")
    command_id = models.UUIDField()
    operation = models.CharField(max_length=40)
    request_fingerprint = models.CharField(max_length=64)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="commands")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["guest", "command_id"], name="unique_guest_command")
        ]
