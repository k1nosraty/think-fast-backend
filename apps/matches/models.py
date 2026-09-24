import uuid
from typing import ClassVar

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

    class Mode(models.TextChoices):
        DUEL = "duel"
        PARTY = "party"

    # Single source of truth for room-mode membership capacity. Party needs one
    # creator plus at least two guessers so placement scoring (1st/2nd/3rd) is
    # meaningful, which is why its minimum is three and not two.
    MINIMUM_MEMBERS: ClassVar[dict[str, int]] = {Mode.DUEL: 2, Mode.PARTY: 3}
    MAXIMUM_MEMBERS: ClassVar[dict[str, int]] = {Mode.DUEL: 2, Mode.PARTY: 8}

    # Default number of rounds requested when a client omits `rounds_count`.
    # Only Party Matches use it; Duel and Solo Matches are always one round.
    DEFAULT_ROUNDS: ClassVar[int] = 5

    # Authoritative per-mode round choices. Party offers 3/5/7 (product rule);
    # Duel/Solo are single-round. Published in the Room contract so clients stop
    # mirroring it (FT-01).
    ALLOWED_ROUNDS: ClassVar[dict[str, list[int]]] = {
        Mode.DUEL: [1],
        Mode.PARTY: [3, 5, 7],
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    join_code = models.CharField(max_length=6, unique=True)
    host = models.ForeignKey(GuestIdentity, on_delete=models.PROTECT, related_name="hosted_rooms")
    preset_id = models.CharField(max_length=50)
    challenge_source = models.CharField(
        max_length=20, choices=ChallengeSource, default=ChallengeSource.SYSTEM
    )
    room_mode = models.CharField(max_length=20, choices=Mode, default=Mode.DUEL)
    rounds_count = models.PositiveIntegerField(default=DEFAULT_ROUNDS)
    state = models.CharField(max_length=20, choices=State, default=State.WAITING)
    latest_sequence = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def minimum_members(cls, room_mode: str) -> int:
        """Ready players required before a Match may start in this mode."""
        return cls.MINIMUM_MEMBERS.get(room_mode, cls.MINIMUM_MEMBERS[cls.Mode.PARTY])

    @classmethod
    def maximum_members(cls, room_mode: str) -> int:
        """Membership ceiling for this mode."""
        return cls.MAXIMUM_MEMBERS.get(room_mode, cls.MAXIMUM_MEMBERS[cls.Mode.PARTY])

    @classmethod
    def allowed_rounds(cls, room_mode: str) -> list[int]:
        """Round-count choices the client may offer for this mode."""
        return list(cls.ALLOWED_ROUNDS.get(room_mode, cls.ALLOWED_ROUNDS[cls.Mode.PARTY]))


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
    round_state = models.CharField(max_length=30, default="active")
    round_number = models.PositiveIntegerField(default=1)
    total_rounds = models.PositiveIntegerField(default=5)
    creator = models.ForeignKey(
        "Participant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_matches",
    )
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
    score = models.PositiveIntegerField(default=0)
    round_score = models.PositiveIntegerField(default=0)
    round_rank = models.PositiveIntegerField(null=True, blank=True)
    is_creator = models.BooleanField(default=False)
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
    round_number = models.PositiveIntegerField(default=1)
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
                fields=["match", "round_number"],
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
    round_number = models.PositiveIntegerField(default=1)
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
                fields=["participant", "round_number", "ordinal"],
                name="unique_participant_round_ordinal",
            ),
        ]
        ordering = ["ordinal"]


class Result(models.Model):
    class Reason(models.TextChoices):
        """Canonical vocabulary for how a Match ended.

        This is the single source of truth for ``Result.reason``. It is mirrored
        by ``contracts/schemas/snapshot.schema.json`` and by the frontend
        ``resultSchema``; a new value must be added here first and then to both
        mirrors, otherwise a real Snapshot will fail contract validation.
        """

        SOLVED = "solved"
        DEADLINE = "deadline"
        ATTEMPT_LIMIT = "attempt_limit"
        ABANDONED = "abandoned"
        NOT_ENOUGH_PLAYERS = "not_enough_players"
        VOIDED = "voided"

    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, primary_key=True, related_name="result"
    )
    outcome = models.CharField(max_length=20)
    reason = models.CharField(max_length=20, choices=Reason)
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
        # The reliability worker scans for unpublished events every second on an
        # append-only table. A partial index keeps that scan off the full table
        # without taxing the hot write path (inserts only, rare updates).
        indexes = [
            models.Index(
                fields=["next_attempt_at"],
                name="matchevent_outbox_due_idx",
                condition=models.Q(published_at__isnull=True),
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
        indexes = [
            models.Index(
                fields=["next_attempt_at"],
                name="roomevent_outbox_due_idx",
                condition=models.Q(published_at__isnull=True),
            )
        ]
        ordering = ["sequence"]
