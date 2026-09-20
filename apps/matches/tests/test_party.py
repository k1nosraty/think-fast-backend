import json
import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.matches.errors import GameAPIError
from apps.matches.models import Match, MatchEvent, Participant, Result, Room
from apps.matches.party import (
    advance_party_round,
    commit_party_secret,
    finish_party_round,
    submit_party_guess,
)
from apps.matches.projections import snapshot
from apps.matches.rooms import create_room, join_room, set_ready, start_room
from apps.matches.services import abandon, activate_countdown, refresh_match_state
from apps.realtime.lifecycle import claim_connection, expire_disconnect_grace
from apps.realtime.recovery import sweep_reliability


def _party_with(
    host: GuestIdentity, *guests: GuestIdentity, rounds_count: int = 3
) -> tuple[Room, Match]:
    room, _ = create_room(
        guest=host,
        command_id=uuid.uuid4(),
        preset_id="number_classic_5_v1",
        challenge_source=Room.ChallengeSource.PLAYERS,
        room_mode="party",
        rounds_count=rounds_count,
    )
    for g in guests:
        join_room(guest=g, room_id=room.id, command_id=uuid.uuid4())
    for g in (host, *guests):
        set_ready(guest=g, room_id=room.id, command_id=uuid.uuid4(), ready=True)
    match, _ = start_room(guest=host, room_id=room.id, command_id=uuid.uuid4())
    return room, match


class PartyModeTests(TestCase):
    def setUp(self) -> None:
        self.host, _ = GuestIdentity.issue(display_name="HostPlayer", avatar_id="avatar1")
        self.p2, _ = GuestIdentity.issue(display_name="PlayerTwo", avatar_id="avatar2")
        self.p3, _ = GuestIdentity.issue(display_name="PlayerThree", avatar_id="avatar3")
        self.p4, _ = GuestIdentity.issue(display_name="PlayerFour", avatar_id="avatar4")

    def test_party_room_supports_up_to_8_players(self) -> None:
        room, _ = create_room(
            guest=self.host,
            command_id=uuid.uuid4(),
            preset_id="number_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
            room_mode="party",
            rounds_count=5,
        )
        self.assertEqual(room.room_mode, "party")
        self.assertEqual(room.rounds_count, 5)

        for i in range(2, 9):
            guest, _ = GuestIdentity.issue(display_name=f"Player{i}", avatar_id=f"avatar{i}")
            join_room(guest=guest, room_id=room.id, command_id=uuid.uuid4())

        self.assertEqual(room.memberships.count(), 8)

        p9, _ = GuestIdentity.issue(display_name="Player9", avatar_id="avatar9")
        with self.assertRaises(GameAPIError) as ctx:
            join_room(guest=p9, room_id=room.id, command_id=uuid.uuid4())
        self.assertEqual(ctx.exception.default_code, "room_full")

    def test_party_room_requires_three_ready_players_to_start(self) -> None:
        room, _ = create_room(
            guest=self.host,
            command_id=uuid.uuid4(),
            preset_id="number_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
            room_mode="party",
            rounds_count=3,
        )
        join_room(guest=self.p2, room_id=room.id, command_id=uuid.uuid4())
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)

        with self.assertRaises(GameAPIError) as ctx:
            start_room(guest=self.host, room_id=room.id, command_id=uuid.uuid4())
        self.assertEqual(ctx.exception.default_code, "not_ready")

        join_room(guest=self.p3, room_id=room.id, command_id=uuid.uuid4())
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p3, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        match, _ = start_room(guest=self.host, room_id=room.id, command_id=uuid.uuid4())
        self.assertEqual(match.participants.count(), 3)

    def test_party_lifecycle_end_to_end(self) -> None:
        room, _ = create_room(
            guest=self.host,
            command_id=uuid.uuid4(),
            preset_id="number_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
            room_mode="party",
            rounds_count=3,
        )
        join_room(guest=self.p2, room_id=room.id, command_id=uuid.uuid4())
        join_room(guest=self.p3, room_id=room.id, command_id=uuid.uuid4())

        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p3, room_id=room.id, command_id=uuid.uuid4(), ready=True)

        match, _ = start_room(guest=self.host, room_id=room.id, command_id=uuid.uuid4())
        self.assertEqual(match.round_number, 1)
        self.assertEqual(match.total_rounds, 3)
        self.assertEqual(match.round_state, "creator_setup")
        self.assertEqual(match.creator.guest_id, self.host.id)

        host_snap = snapshot(match, self.host)
        self.assertIn("commit_challenge", host_snap["available_actions"])
        self.assertEqual(host_snap["round_number"], 1)

        p2_snap = snapshot(match, self.p2)
        self.assertNotIn("commit_challenge", p2_snap["available_actions"])

        with self.assertRaises(GameAPIError) as ctx:
            commit_party_secret(
                guest=self.p2,
                match_id=match.id,
                command_id=uuid.uuid4(),
                secret="72941",
            )
        self.assertEqual(ctx.exception.default_code, "not_creator")

        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        match.refresh_from_db()
        from django.conf import settings

        expected_state = (
            Match.State.COUNTDOWN
            if getattr(settings, "FRIENDLY_COUNTDOWN_SECONDS", 5) > 0
            else Match.State.ACTIVE
        )
        self.assertEqual(match.state, expected_state)

        active_time = now + timedelta(seconds=4)
        with self.assertRaises(GameAPIError) as ctx:
            submit_party_guess(
                guest=self.host,
                match_id=match.id,
                command_id=uuid.uuid4(),
                guess="72941",
                now=active_time,
            )
        self.assertEqual(ctx.exception.default_code, "creator_cannot_guess")

        attempt_p3, match, _ = submit_party_guess(
            guest=self.p3,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="78345",
            now=active_time,
        )
        self.assertEqual(
            attempt_p3.feedback["positions"], ["exact", "absent", "absent", "exact", "absent"]
        )
        self.assertFalse(attempt_p3.solved)

        attempt_p2, match, _ = submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="72941",
            now=active_time + timedelta(seconds=5),
        )
        self.assertTrue(attempt_p2.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")
        attempt_p3_final, match, _ = submit_party_guess(
            guest=self.p3,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="72941",
            now=active_time + timedelta(seconds=6),
        )
        self.assertTrue(attempt_p3_final.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "round_finished")

        part_p2 = match.participants.get(guest=self.p2)
        part_p3 = match.participants.get(guest=self.p3)
        part_host = match.participants.get(guest=self.host)

        self.assertEqual(part_p2.score, 100)
        self.assertEqual(part_p2.round_score, 100)
        self.assertEqual(part_p3.score, 75)
        self.assertGreater(part_host.score, 0)

        p2_finish_snap = snapshot(match, self.p2)
        self.assertEqual(p2_finish_snap["result"]["revealed_secret"], "72941")
        self.assertIn("next_round", p2_finish_snap["available_actions"])

        advance_command = uuid.uuid4()
        match = advance_party_round(guest=self.p2, match_id=match.id, command_id=advance_command)
        self.assertEqual(match.round_number, 2)
        self.assertEqual(match.round_state, "creator_setup")
        self.assertEqual(match.creator.guest_id, self.p2.id)
        self.assertIsNone(snapshot(match, self.p2)["result"])

        part_p2_r2 = match.participants.get(guest=self.p2)
        self.assertTrue(part_p2_r2.is_creator)
        self.assertEqual(part_p2_r2.attempt_count, 0)

        replay = advance_party_round(guest=self.p2, match_id=match.id, command_id=advance_command)
        self.assertEqual(replay.round_number, 2)

    def test_party_two_rounds_with_real_guesses_in_every_round(self) -> None:
        """Regression: attempt ordinals are unique per participant per round, so
        a guesser who already used ordinal=1 in round 1 may reuse ordinal=1 in
        round 2 after advance_party_round resets attempt_count to 0."""
        room, _ = create_room(
            guest=self.host,
            command_id=uuid.uuid4(),
            preset_id="number_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
            room_mode="party",
            rounds_count=3,
        )
        join_room(guest=self.p2, room_id=room.id, command_id=uuid.uuid4())
        join_room(guest=self.p3, room_id=room.id, command_id=uuid.uuid4())
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p3, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        match, _ = start_room(guest=self.host, room_id=room.id, command_id=uuid.uuid4())
        self.assertEqual(match.round_number, 1)
        self.assertEqual(match.creator.guest_id, self.host.id)

        now = timezone.now()

        # Round 1: host creates, p2 and p3 (both guessers) submit real guesses.
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        t = now + timedelta(seconds=1)
        attempt_p2, match, _ = submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="78345",
            now=t,
        )
        self.assertEqual(attempt_p2.ordinal, 1)
        self.assertEqual(attempt_p2.round_number, 1)
        self.assertFalse(attempt_p2.solved)

        t += timedelta(seconds=1)
        attempt_p3, match, _ = submit_party_guess(
            guest=self.p3,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="72941",
            now=t,
        )
        self.assertTrue(attempt_p3.solved)
        self.assertEqual(attempt_p3.ordinal, 1)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

        t += timedelta(seconds=1)
        attempt_p2_final, match, _ = submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="72941",
            now=t,
        )
        self.assertTrue(attempt_p2_final.solved)
        self.assertEqual(attempt_p2_final.ordinal, 2)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "round_finished")

        # Advance to round 2; every participant's attempt_count resets to 0.
        match = advance_party_round(guest=self.p2, match_id=match.id, command_id=uuid.uuid4())
        self.assertEqual(match.round_number, 2)
        self.assertEqual(match.creator.guest_id, self.p2.id)
        for participant in match.participants.all():
            self.assertEqual(participant.attempt_count, 0)

        # Round 2: p2 creates; host and p3 guess again. p3 reuses ordinal 1,
        # which previously violated unique (participant, ordinal).
        commit_party_secret(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="45291",
            now=now + timedelta(seconds=1),
        )
        t += timedelta(seconds=1)
        attempt_host, match, _ = submit_party_guess(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="78123",
            now=t,
        )
        self.assertEqual(attempt_host.ordinal, 1)
        self.assertEqual(attempt_host.round_number, 2)
        self.assertFalse(attempt_host.solved)

        t += timedelta(seconds=1)
        attempt_p3_r2, match, _ = submit_party_guess(
            guest=self.p3,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="45291",
            now=t,
        )
        self.assertTrue(attempt_p3_r2.solved)
        self.assertEqual(attempt_p3_r2.ordinal, 1)
        self.assertEqual(attempt_p3_r2.round_number, 2)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

        t += timedelta(seconds=1)
        attempt_host_r2, match, _ = submit_party_guess(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="45291",
            now=t,
        )
        self.assertTrue(attempt_host_r2.solved)
        self.assertEqual(attempt_host_r2.ordinal, 2)
        self.assertEqual(attempt_host_r2.round_number, 2)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "round_finished")

    def test_party_guess_command_id_conflict_is_rejected(self) -> None:
        room, _ = create_room(
            guest=self.host,
            command_id=uuid.uuid4(),
            preset_id="number_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
            room_mode="party",
            rounds_count=3,
        )
        join_room(guest=self.p2, room_id=room.id, command_id=uuid.uuid4())
        join_room(guest=self.p3, room_id=room.id, command_id=uuid.uuid4())
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p3, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        match, _ = start_room(guest=self.host, room_id=room.id, command_id=uuid.uuid4())
        now = timezone.now()
        commit_party_secret(
            guest=self.host, match_id=match.id, command_id=uuid.uuid4(), secret="72941", now=now
        )
        command_id = uuid.uuid4()
        submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=command_id,
            guess="78345",
            now=now + timedelta(seconds=4),
        )
        with self.assertRaises(GameAPIError) as ctx:
            submit_party_guess(
                guest=self.p2,
                match_id=match.id,
                command_id=command_id,
                guess="72941",
                now=now + timedelta(seconds=5),
            )
        self.assertEqual(ctx.exception.default_code, "idempotency_conflict")

    def test_color_party_mode(self) -> None:
        room, _ = create_room(
            guest=self.host,
            command_id=uuid.uuid4(),
            preset_id="color_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
            room_mode="party",
            rounds_count=3,
        )
        join_room(guest=self.p2, room_id=room.id, command_id=uuid.uuid4())
        join_room(guest=self.p3, room_id=room.id, command_id=uuid.uuid4())
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p3, room_id=room.id, command_id=uuid.uuid4(), ready=True)

        match, _ = start_room(guest=self.host, room_id=room.id, command_id=uuid.uuid4())
        now = timezone.now()
        color_secret = ["red", "green", "blue", "yellow", "orange"]
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret=color_secret,
            now=now,
        )

        active_time = now + timedelta(seconds=4)
        attempt, match, _ = submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess=color_secret,
            now=active_time,
        )
        self.assertTrue(attempt.solved)
        attempt_p3, match, _ = submit_party_guess(
            guest=self.p3,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess=color_secret,
            now=active_time + timedelta(seconds=1),
        )
        self.assertTrue(attempt_p3.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "round_finished")
        p2_snap = snapshot(match, self.p2)
        self.assertEqual(p2_snap["result"]["revealed_secret"], color_secret)

    def test_secret_never_leaks_before_reveal(self) -> None:
        room, _ = create_room(
            guest=self.host,
            command_id=uuid.uuid4(),
            preset_id="number_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
            room_mode="party",
            rounds_count=3,
        )
        join_room(guest=self.p2, room_id=room.id, command_id=uuid.uuid4())
        join_room(guest=self.p3, room_id=room.id, command_id=uuid.uuid4())
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p3, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        match, _ = start_room(guest=self.host, room_id=room.id, command_id=uuid.uuid4())

        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="98765",
            now=now,
        )

        p2_snap = snapshot(match, self.p2)
        self.assertNotIn("revealed_secret", p2_snap.get("result") or {})
        self.assertIsNone(p2_snap.get("result"))

        import json

        snap_json = json.dumps(p2_snap)
        self.assertNotIn("98765", snap_json)

    def test_round_deadline_timeout_awards_creator(self) -> None:
        room, _ = create_room(
            guest=self.host,
            command_id=uuid.uuid4(),
            preset_id="number_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
            room_mode="party",
            rounds_count=3,
        )
        join_room(guest=self.p2, room_id=room.id, command_id=uuid.uuid4())
        join_room(guest=self.p3, room_id=room.id, command_id=uuid.uuid4())
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p3, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        match, _ = start_room(guest=self.host, room_id=room.id, command_id=uuid.uuid4())

        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )

        expired_time = match.deadline + timedelta(seconds=1)
        finish_party_round(match, reason="deadline", now=expired_time)
        match.refresh_from_db()

        self.assertEqual(match.round_state, "round_finished")
        host_part = match.participants.get(guest=self.host)
        p2_part = match.participants.get(guest=self.p2)

        self.assertEqual(host_part.round_score, 80)
        self.assertEqual(p2_part.round_score, 0)
        self.assertEqual(p2_part.solve_state, Participant.SolveState.UNSOLVED)

    def test_http_party_endpoints(self) -> None:
        from rest_framework.test import APIClient

        client_host = APIClient()
        client_host.force_authenticate(user=self.host)
        client_p2 = APIClient()
        client_p2.force_authenticate(user=self.p2)
        client_p3 = APIClient()
        client_p3.force_authenticate(user=self.p3)

        resp = client_host.post(
            "/api/v1/rooms/",
            {
                "command_id": str(uuid.uuid4()),
                "preset_id": "number_classic_5_v1",
                "challenge_source": "players",
                "room_mode": "party",
                "rounds_count": 3,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        room_id = resp.data["room_id"]

        join_resp = client_p2.post(
            f"/api/v1/rooms/{room_id}/join/",
            {"command_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(join_resp.status_code, 200)

        join_p3_resp = client_p3.post(
            f"/api/v1/rooms/{room_id}/join/",
            {"command_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(join_p3_resp.status_code, 200)

        client_host.post(
            f"/api/v1/rooms/{room_id}/ready/",
            {"command_id": str(uuid.uuid4()), "ready": True},
            format="json",
        )
        client_p2.post(
            f"/api/v1/rooms/{room_id}/ready/",
            {"command_id": str(uuid.uuid4()), "ready": True},
            format="json",
        )
        client_p3.post(
            f"/api/v1/rooms/{room_id}/ready/",
            {"command_id": str(uuid.uuid4()), "ready": True},
            format="json",
        )

        start_resp = client_host.post(
            f"/api/v1/rooms/{room_id}/start/", {"command_id": str(uuid.uuid4())}, format="json"
        )
        self.assertEqual(start_resp.status_code, 201)
        match_id = start_resp.data["match_id"]

        commit_resp = client_host.post(
            f"/api/v1/matches/{match_id}/challenges/",
            {"command_id": str(uuid.uuid4()), "secret": "72941"},
            format="json",
        )
        self.assertIn(commit_resp.status_code, (200, 201))

        guess_resp = client_p2.post(
            f"/api/v1/matches/{match_id}/guesses/",
            {"command_id": str(uuid.uuid4()), "guess": "72941"},
            format="json",
        )
        self.assertIn(guess_resp.status_code, (200, 201))
        self.assertTrue(guess_resp.data["solved"])

        guess_p3_resp = client_p3.post(
            f"/api/v1/matches/{match_id}/guesses/",
            {"command_id": str(uuid.uuid4()), "guess": "72941"},
            format="json",
        )
        self.assertIn(guess_p3_resp.status_code, (200, 201))
        self.assertTrue(guess_p3_resp.data["solved"])

        next_resp = client_p2.post(
            f"/api/v1/matches/{match_id}/next-round/",
            {"command_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(next_resp.status_code, 200)
        self.assertEqual(next_resp.data["round_number"], 2)

    @override_settings(FRIENDLY_COUNTDOWN_SECONDS=5)
    def test_party_countdown_activation_via_snapshot_refresh_accepts_guess(self) -> None:
        """Bug 1: a countdown Party round is activated by snapshot refresh with
        round_state moved to 'active' and a Party-shaped round.started event."""
        _, match = _party_with(self.host, self.p2, self.p3)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.COUNTDOWN)
        self.assertEqual(match.round_state, "countdown")

        guest_snap = snapshot(match, self.p2)
        self.assertNotIn("submit_guess", guest_snap["available_actions"])

        refresh_match_state(guest=self.host, match_id=match.id, now=match.started_at)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ACTIVE)
        self.assertEqual(match.round_state, "active")
        started_events = MatchEvent.objects.filter(match=match, event_type="round.started")
        self.assertEqual(started_events.count(), 1)
        self.assertEqual(started_events.first().payload["round_number"], 1)
        self.assertEqual(
            started_events.first().payload["started_at"],
            match.started_at.isoformat().replace("+00:00", "Z"),
        )
        self.assertEqual(
            started_events.first().payload["deadline"],
            match.deadline.isoformat().replace("+00:00", "Z"),
        )
        self.assertNotIn("72941", json.dumps(started_events.first().payload))

        guest_snap = snapshot(match, self.p2)
        self.assertIn("submit_guess", guest_snap["available_actions"])
        host_snap = snapshot(match, self.host)
        self.assertNotIn("submit_guess", host_snap["available_actions"])

        attempt, match, _ = submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="78345",
            now=match.started_at + timedelta(seconds=1),
        )
        self.assertFalse(attempt.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

    @override_settings(FRIENDLY_COUNTDOWN_SECONDS=5)
    def test_party_countdown_activation_via_websocket_helper(self) -> None:
        """Bug 1: the WebSocket countdown path activates a Party round to
        round_state 'active' and emits round.started."""
        _, match = _party_with(self.host, self.p2, self.p3)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.COUNTDOWN)
        self.assertEqual(match.round_state, "countdown")

        activate_countdown(match.id, now=match.started_at + timedelta(seconds=1))
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ACTIVE)
        self.assertEqual(match.round_state, "active")
        started_events = MatchEvent.objects.filter(match=match, event_type="round.started")
        self.assertEqual(started_events.count(), 1)
        attempt, match, _ = submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="78345",
            now=match.started_at + timedelta(seconds=2),
        )
        self.assertFalse(attempt.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

    @override_settings(FRIENDLY_COUNTDOWN_SECONDS=5)
    def test_party_guess_submission_activates_countdown_and_is_accepted(self) -> None:
        """Bug 1: a Party guess after started_at self-activates the round and
        is accepted (round_state never stays 'countdown' while state is ACTIVE)."""
        _, match = _party_with(self.host, self.p2, self.p3)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.COUNTDOWN)

        attempt, match, _ = submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="78345",
            now=match.started_at + timedelta(seconds=1),
        )
        self.assertIsNotNone(attempt)
        self.assertFalse(attempt.solved)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ACTIVE)
        self.assertEqual(match.round_state, "active")
        self.assertEqual(
            MatchEvent.objects.filter(match=match, event_type="round.started").count(), 1
        )

    def test_party_deadline_finalizes_round_via_party_finalizer(self) -> None:
        """Bug 2: deadline enforcement for a Party match runs the Party round
        finalizer, not the 1v1 friendly finalizer."""
        room, match = _party_with(self.host, self.p2, self.p3)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ACTIVE)
        self.assertEqual(match.round_state, "active")

        Match.objects.filter(pk=match.id).update(deadline=timezone.now() - timedelta(seconds=1))
        refresh_match_state(guest=self.host, match_id=match.id, now=timezone.now())
        match.refresh_from_db()

        self.assertEqual(match.round_state, "round_finished")
        result = Result.objects.get(match=match)
        self.assertEqual(result.reason, "deadline")
        self.assertEqual(result.outcome, "unsolved")
        self.assertTrue(result.secret_revealed)
        self.assertEqual(match.participants.get(guest=self.host).round_score, 80)
        self.assertEqual(
            match.participants.get(guest=self.p2).solve_state, Participant.SolveState.UNSOLVED
        )
        self.assertEqual(match.participants.get(guest=self.p2).round_score, 0)
        self.assertTrue(
            MatchEvent.objects.filter(match=match, event_type="round.finished").exists()
        )
        self.assertTrue(
            MatchEvent.objects.filter(match=match, event_type="scores.updated").exists()
        )
        room.refresh_from_db()
        self.assertEqual(room.state, Room.State.ACTIVE)

    def test_party_deadline_sweep_finalizes_round(self) -> None:
        """Bug 2: the reliability sweep converges a due Party round deadline
        through the Party finalizer."""
        room, match = _party_with(self.host, self.p2, self.p3)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        Match.objects.filter(pk=match.id).update(deadline=timezone.now() - timedelta(seconds=1))
        sweep_reliability(limit=100)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "round_finished")
        self.assertEqual(Result.objects.get(match=match).reason, "deadline")
        room.refresh_from_db()
        self.assertEqual(room.state, Room.State.ACTIVE)

    def test_party_guesser_leaving_mid_round_continues_round(self) -> None:
        """Bug 3: a single departure from a 4-player Party match abandons only
        the departing player while enough guessers remain."""
        room, match = _party_with(self.host, self.p2, self.p3, self.p4)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

        abandon(guest=self.p4, match_id=match.id, command_id=uuid.uuid4(), now=now)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ACTIVE)
        self.assertEqual(match.round_state, "active")
        p4_part = match.participants.get(guest=self.p4)
        self.assertEqual(p4_part.solve_state, Participant.SolveState.ABANDONED)

        t = now + timedelta(seconds=1)
        attempt_p2, match, _ = submit_party_guess(
            guest=self.p2, match_id=match.id, command_id=uuid.uuid4(), guess="72941", now=t
        )
        self.assertTrue(attempt_p2.solved)
        attempt_p3, match, _ = submit_party_guess(
            guest=self.p3,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="72941",
            now=t + timedelta(seconds=1),
        )
        self.assertTrue(attempt_p3.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "round_finished")
        self.assertEqual(match.participants.get(guest=self.p2).round_score, 100)
        self.assertEqual(match.participants.get(guest=self.p4).round_score, 0)
        room.refresh_from_db()
        self.assertEqual(room.state, Room.State.ACTIVE)

    def test_party_last_playing_guesser_leaving_finishes_round(self) -> None:
        """Bug 3: when the last PLAYING guesser leaves, the round finalizes
        instead of stalling."""
        _, match = _party_with(self.host, self.p2, self.p3, self.p4)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        t = now + timedelta(seconds=1)
        attempt_p2, match, _ = submit_party_guess(
            guest=self.p2, match_id=match.id, command_id=uuid.uuid4(), guess="72941", now=t
        )
        self.assertTrue(attempt_p2.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")
        attempt_p3, match, _ = submit_party_guess(
            guest=self.p3,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="72941",
            now=t + timedelta(seconds=1),
        )
        self.assertTrue(attempt_p3.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

        abandon(
            guest=self.p4,
            match_id=match.id,
            command_id=uuid.uuid4(),
            now=t + timedelta(seconds=2),
        )
        match.refresh_from_db()
        self.assertEqual(match.round_state, "round_finished")
        result = Result.objects.get(match=match)
        self.assertEqual(result.reason, "abandoned")
        self.assertEqual(result.outcome, "won")
        self.assertEqual(match.participants.get(guest=self.p2).round_score, 100)
        self.assertEqual(match.participants.get(guest=self.p3).round_score, 75)
        self.assertEqual(match.participants.get(guest=self.p4).round_score, 0)

    def test_party_creator_leaving_during_setup_reassigns_creator(self) -> None:
        """Bug 3: creator departure during creator setup reassigns the role to
        the next eligible player and resets the setup window; the round is not
        stranded and the old creator cannot commit."""
        _, match = _party_with(self.host, self.p2, self.p3, self.p4)
        self.assertEqual(match.creator.guest_id, self.host.id)
        self.assertEqual(match.round_state, "creator_setup")
        now = timezone.now()

        abandon(guest=self.host, match_id=match.id, command_id=uuid.uuid4(), now=now)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.SETUP)
        self.assertEqual(match.round_state, "creator_setup")
        self.assertEqual(match.creator.guest_id, self.p2.id)
        self.assertGreater(match.setup_expires_at, now)
        host_part = match.participants.get(guest=self.host)
        self.assertEqual(host_part.solve_state, Participant.SolveState.ABANDONED)
        self.assertFalse(host_part.is_creator)
        p2_part = match.participants.get(guest=self.p2)
        self.assertTrue(p2_part.is_creator)
        self.assertTrue(
            MatchEvent.objects.filter(match=match, event_type="creator.rotated").exists()
        )
        self.assertTrue(
            MatchEvent.objects.filter(match=match, event_type="challenge.setup_started").exists()
        )

        setup = snapshot(match, self.p2)["challenge_setup"]
        self.assertEqual(setup["creator_participant_id"], str(p2_part.id))
        self.assertEqual(setup["is_creator"], True)

        with self.assertRaises(GameAPIError) as ctx:
            commit_party_secret(
                guest=self.host,
                match_id=match.id,
                command_id=uuid.uuid4(),
                secret="72941",
                now=now,
            )
        self.assertEqual(ctx.exception.default_code, "not_creator")

        match, _ = commit_party_secret(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="45291",
            now=now,
        )
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

    def test_party_below_minimum_terminates_when_guesser_leaves_active(self) -> None:
        """Bug 3: a 3-player Party match that drops to 2 active players
        terminates with a clear terminal outcome instead of stalling."""
        room, match = _party_with(self.host, self.p2, self.p3)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

        abandon(guest=self.p3, match_id=match.id, command_id=uuid.uuid4(), now=now)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ABANDONED)
        self.assertEqual(match.round_state, "match_finished")
        result = Result.objects.get(match=match)
        self.assertEqual(result.outcome, "abandoned")
        self.assertEqual(result.reason, "not_enough_players")
        self.assertFalse(result.secret_revealed)
        finished_payload = MatchEvent.objects.get(match=match, event_type="match.finished").payload
        self.assertNotIn("72941", json.dumps(finished_payload))

        room.refresh_from_db()
        self.assertEqual(room.state, Room.State.READY_CHECK)
        self.assertFalse(any(member.ready for member in room.memberships.all()))
        p3_part = match.participants.get(guest=self.p3)
        self.assertEqual(p3_part.solve_state, Participant.SolveState.ABANDONED)

    def test_party_below_minimum_terminates_when_creator_leaves_setup(self) -> None:
        """Bug 3: a 3-player Party match whose creator leaves during setup
        cannot reset a creator (no eligible successor remains), so the match
        terminates with a clear terminal outcome instead of being stranded."""
        room, match = _party_with(self.host, self.p2, self.p3)
        now = timezone.now()
        abandon(guest=self.host, match_id=match.id, command_id=uuid.uuid4(), now=now)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ABANDONED)
        self.assertEqual(match.round_state, "match_finished")
        self.assertEqual(Result.objects.get(match=match).reason, "not_enough_players")
        room.refresh_from_db()
        self.assertEqual(room.state, Room.State.READY_CHECK)

    def test_party_creator_leaving_mid_round_keeps_computed_score(self) -> None:
        """Bug 3: the creator departing after committing the secret leaves the
        committed round to finish normally; the existing scoring rules still
        award the creator their computed round score."""
        _, match = _party_with(self.host, self.p2, self.p3, self.p4)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ACTIVE)

        abandon(guest=self.host, match_id=match.id, command_id=uuid.uuid4(), now=now)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ACTIVE)
        self.assertEqual(match.round_state, "active")
        self.assertEqual(
            match.participants.get(guest=self.host).solve_state,
            Participant.SolveState.ABANDONED,
        )

        t = now + timedelta(seconds=1)
        for g in (self.p2, self.p3, self.p4):
            submit_party_guess(
                guest=g,
                match_id=match.id,
                command_id=uuid.uuid4(),
                guess="72941",
                now=t,
            )
            t += timedelta(seconds=1)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "round_finished")
        host_part = match.participants.get(guest=self.host)
        self.assertEqual(host_part.round_score, 20)
        self.assertEqual(host_part.score, 20)
        self.assertEqual(host_part.solve_state, Participant.SolveState.ABANDONED)

    def test_party_disconnect_grace_expiry_continues_round(self) -> None:
        """Bug 3: a Party player whose disconnect grace expires is marked
        ABANDONED but the match keeps running the round."""
        _, match = _party_with(self.host, self.p2, self.p3, self.p4)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        part_p4 = match.participants.get(guest=self.p4)
        connection_id = uuid.uuid4()
        claim_connection(
            participant_id=part_p4.id, connection_id=connection_id, channel_name="some"
        )
        Participant.objects.filter(pk=part_p4.pk).update(
            connected=False, grace_expires_at=now - timedelta(seconds=1)
        )
        expired = expire_disconnect_grace(
            participant_id=part_p4.id, connection_id=connection_id, now=now
        )
        self.assertTrue(expired)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ACTIVE)
        self.assertEqual(match.round_state, "active")
        self.assertEqual(
            match.participants.get(guest=self.p4).solve_state,
            Participant.SolveState.ABANDONED,
        )

        attempt, match, _ = submit_party_guess(
            guest=self.p2,
            match_id=match.id,
            command_id=uuid.uuid4(),
            guess="72941",
            now=now + timedelta(seconds=1),
        )
        self.assertTrue(attempt.solved)
        match.refresh_from_db()
        self.assertEqual(match.round_state, "active")

    def test_party_disconnect_grace_expiry_below_minimum_terminates(self) -> None:
        """Bug 3: grace expiry that drops a 3-player Party to 2 active players
        terminates the whole match with a terminal outcome and reveals no
        secret."""
        _, match = _party_with(self.host, self.p2, self.p3)
        now = timezone.now()
        commit_party_secret(
            guest=self.host,
            match_id=match.id,
            command_id=uuid.uuid4(),
            secret="72941",
            now=now,
        )
        part_p3 = match.participants.get(guest=self.p3)
        connection_id = uuid.uuid4()
        claim_connection(
            participant_id=part_p3.id, connection_id=connection_id, channel_name="some"
        )
        Participant.objects.filter(pk=part_p3.pk).update(
            connected=False, grace_expires_at=now - timedelta(seconds=1)
        )
        expired = expire_disconnect_grace(
            participant_id=part_p3.id, connection_id=connection_id, now=now
        )
        self.assertTrue(expired)
        match.refresh_from_db()
        self.assertEqual(match.state, Match.State.ABANDONED)
        result = Result.objects.get(match=match)
        self.assertEqual(result.reason, "not_enough_players")
        self.assertFalse(result.secret_revealed)
        self.assertNotIn(
            "72941",
            json.dumps(MatchEvent.objects.get(match=match, event_type="match.finished").payload),
        )
