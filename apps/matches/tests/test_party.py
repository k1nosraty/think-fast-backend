import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.matches.errors import GameAPIError
from apps.matches.models import Match, Participant, Room
from apps.matches.party import (
    advance_party_round,
    commit_party_secret,
    finish_party_round,
    submit_party_guess,
)
from apps.matches.projections import snapshot
from apps.matches.rooms import create_room, join_room, set_ready, start_room


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
            if getattr(settings, "FRIENDLY_COUNTDOWN_SECONDS", 3) > 0
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
        self.assertEqual(match.round_state, "round_finished")

        part_p2 = match.participants.get(guest=self.p2)
        part_p3 = match.participants.get(guest=self.p3)
        part_host = match.participants.get(guest=self.host)

        self.assertEqual(part_p2.score, 100)
        self.assertEqual(part_p2.round_score, 100)
        self.assertEqual(part_p3.score, 0)
        self.assertGreater(part_host.score, 0)

        p2_finish_snap = snapshot(match, self.p2)
        self.assertEqual(p2_finish_snap["result"]["revealed_secret"], "72941")
        self.assertIn("next_round", p2_finish_snap["available_actions"])

        match = advance_party_round(guest=self.p2, match_id=match.id)
        self.assertEqual(match.round_number, 2)
        self.assertEqual(match.round_state, "creator_setup")
        self.assertEqual(match.creator.guest_id, self.p2.id)

        part_p2_r2 = match.participants.get(guest=self.p2)
        self.assertTrue(part_p2_r2.is_creator)
        self.assertEqual(part_p2_r2.attempt_count, 0)

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
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)

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
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
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
        set_ready(guest=self.host, room_id=room.id, command_id=uuid.uuid4(), ready=True)
        set_ready(guest=self.p2, room_id=room.id, command_id=uuid.uuid4(), ready=True)
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

        next_resp = client_p2.post(f"/api/v1/matches/{match_id}/next-round/", format="json")
        self.assertEqual(next_resp.status_code, 200)
        self.assertEqual(next_resp.data["round_number"], 2)
