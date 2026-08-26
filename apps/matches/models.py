import uuid

from django.db import models

from apps.accounts.models import GuestIdentity


class Room(models.Model):
    class ChallengeSource(models.TextChoices):
        SYSTEM = "system"
        PLAYERS = "players"

    class State(models.TextChoices):
        WAITING = "waiting"
        READY_CHECK = "ready_check"
        ACTIVE = "active"
        CLOSED = "closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    join_code = models.CharField(max_length=6, unique=True)
    host = models.ForeignKey(GuestIdentity, on_delete=models.PROTECT, related_name="hosted_rooms")
    preset_id = models.CharField(max_length=50)
    challenge_source = models.CharField(
        max_length=20, choices=ChallengeSource, default=ChallengeSource.SYSTEM
    )
    state = models.CharField(max_length=20, choices=State, default=State.WAITING)
    latest_sequence = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RoomMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="memberships")
    guest = models.ForeignKey(
        GuestIdentity, on_delete=models.PROTECT, related_name="room_memberships"
    )
    display_name = models.CharField(max_length=20)
    avatar_id = models.CharField(max_length=50)
    ready = models.BooleanField(default=False)
    connected = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["room", "guest"], name="unique_room_guest")]
        ordering = ["joined_at", "id"]


class Match(models.Model):
    class State(models.TextChoices):
        SETUP = "setup"
        COUNTDOWN = "countdown"
        ACTIVE = "active"
        FINISHING = "finishing"
        FINISHED = "finished"
        ABANDONED = "abandoned"
        CANCELLED = "cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT, related_name="matches", null=True, blank=True
    )
    state = models.CharField(max_length=20, choices=State, default=State.ACTIVE)
    rules = models.JSONField()
    started_at = models.DateTimeField()
    deadline = models.DateTimeField()
    setup_expires_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    finish_due_at = models.DateTimeField(null=True, blank=True)
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
    connected = models.BooleanField(default=False)
    primary_connection_id = models.UUIDField(null=True, blank=True, editable=False)
    primary_channel_name = models.CharField(max_length=255, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    grace_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["match", "guest"], name="unique_match_guest")
        ]


class Challenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="challenges")
    creator = models.ForeignKey(
        Participant,
        on_delete=models.PROTECT,
        related_name="created_challenges",
        null=True,
        blank=True,
    )
    solver = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="assigned_challenges",
        null=True,
        blank=True,
    )
    protected_secret = models.TextField(editable=False)
    committed_at = models.DateTimeField(null=True, blank=True)
    secret_destroyed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["match", "solver"], name="unique_match_solver_challenge"
            ),
            models.UniqueConstraint(
                fields=["match"],
                condition=models.Q(solver__isnull=True),
                name="unique_shared_match_challenge",
            ),
            models.CheckConstraint(
                condition=models.Q(creator__isnull=True)
                | models.Q(solver__isnull=True)
                | ~models.Q(creator=models.F("solver")),
                name="challenge_creator_not_solver",
            ),
        ]


class Attempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="attempts")
    command_id = models.UUIDField()
    request_fingerprint = models.CharField(max_length=64)
    ordinal = models.PositiveIntegerField()
    guess = models.JSONField()
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


class RematchProposal(models.Model):
    class State(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        DECLINED = "declined"
        EXPIRED = "expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="rematch_proposals")
    source_match = models.OneToOneField(
        Match, on_delete=models.CASCADE, related_name="rematch_proposal"
    )
    requester = models.ForeignKey(
        GuestIdentity, on_delete=models.PROTECT, related_name="rematch_requests"
    )
    state = models.CharField(max_length=20, choices=State, default=State.PENDING)
    expires_at = models.DateTimeField()
    new_match = models.OneToOneField(
        Match,
        on_delete=models.SET_NULL,
        related_name="accepted_rematch",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CommandRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guest = models.ForeignKey(GuestIdentity, on_delete=models.CASCADE, related_name="commands")
    command_id = models.UUIDField()
    operation = models.CharField(max_length=40)
    request_fingerprint = models.CharField(max_length=64)
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="commands", null=True, blank=True
    )
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="commands", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["guest", "command_id"], name="unique_guest_command")
        ]


class MatchEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=50)
    visibility = models.CharField(max_length=20)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, null=True, blank=True)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    publish_attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["match", "sequence"], name="unique_match_event_sequence"
            )
        ]
        ordering = ["sequence"]


class RoomEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    publish_attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["room", "sequence"], name="unique_room_event_sequence")
        ]
        ordering = ["sequence"]
