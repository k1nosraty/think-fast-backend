"""Idempotency record and fingerprint management for mutations."""

import hashlib
import json
import uuid

from apps.accounts.models import GuestIdentity
from apps.matches.errors import GameAPIError
from apps.matches.models import CommandRecord


def fingerprint(payload: dict[str, object]) -> str:
    """Compute a deterministic sha256 hash of a JSON-serializable request payload."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def check_command_prior(
    *,
    guest: GuestIdentity,
    command_id: uuid.UUID,
    operation: str,
    request_hash: str,
) -> CommandRecord | None:
    """Validate idempotency for a command_id, ensuring no payload mismatch occurs."""
    prior = CommandRecord.objects.filter(guest=guest, command_id=command_id).first()
    if prior is not None and (
        prior.operation != operation or prior.request_fingerprint != request_hash
    ):
        raise GameAPIError(
            "idempotency_conflict", "Command ID was already used with a different request."
        )
    return prior
