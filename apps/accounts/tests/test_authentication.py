from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.accounts.authentication import GuestAuthentication
from apps.accounts.models import GuestIdentity


@pytest.mark.django_db
def test_missing_authorization_header_returns_none() -> None:
    drf_request = Request(APIRequestFactory().get("/"))
    assert GuestAuthentication().authenticate(drf_request) is None


@pytest.mark.django_db
def test_malformed_header_is_rejected() -> None:
    for header in ["Bearer", "Basic abcdef"]:
        drf_request = Request(APIRequestFactory().get("/"))
        drf_request.META["HTTP_AUTHORIZATION"] = header
        with pytest.raises(AuthenticationFailed, match="bearer authorization"):
            GuestAuthentication().authenticate(drf_request)


@pytest.mark.django_db
def test_undecodable_token_is_rejected() -> None:
    drf_request = Request(APIRequestFactory().get("/"))
    drf_request.META["HTTP_AUTHORIZATION"] = "Bearer \xff\xfe"
    with pytest.raises(AuthenticationFailed, match="Invalid bearer token"):
        GuestAuthentication().authenticate(drf_request)


@pytest.mark.django_db
def test_valid_token_authenticates_guest() -> None:
    _, token = GuestIdentity.issue(display_name="Amir", avatar_id="avatar_01")
    drf_request = Request(APIRequestFactory().get("/"))
    drf_request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    guest, returned_token = GuestAuthentication().authenticate(drf_request)
    assert guest.display_name == "Amir"
    assert returned_token == token


@pytest.mark.django_db
def test_expired_guest_is_rejected() -> None:
    guest, token = GuestIdentity.issue(display_name="Amir", avatar_id="avatar_01")
    GuestIdentity.objects.filter(pk=guest.pk).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    drf_request = Request(APIRequestFactory().get("/"))
    drf_request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    with pytest.raises(AuthenticationFailed, match="invalid or expired"):
        GuestAuthentication().authenticate(drf_request)


@pytest.mark.django_db
def test_revoked_guest_is_rejected() -> None:
    guest, token = GuestIdentity.issue(display_name="Amir", avatar_id="avatar_01")
    GuestIdentity.objects.filter(pk=guest.pk).update(revoked_at=timezone.now())
    drf_request = Request(APIRequestFactory().get("/"))
    drf_request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    with pytest.raises(AuthenticationFailed, match="invalid or expired"):
        GuestAuthentication().authenticate(drf_request)


@pytest.mark.django_db
def test_stale_guest_refreshes_last_seen_and_expiry() -> None:
    _, token = GuestIdentity.issue(display_name="Amir", avatar_id="avatar_01")
    GuestIdentity.objects.filter(token_digest=GuestIdentity.digest_token(token)).update(
        last_seen_at=timezone.now() - timedelta(days=2),
        expires_at=timezone.now() + timedelta(days=1),
    )
    drf_request = Request(APIRequestFactory().get("/"))
    drf_request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    guest, _ = GuestAuthentication().authenticate(drf_request)
    guest.refresh_from_db()
    assert (timezone.now() - guest.last_seen_at).total_seconds() < 60
    assert (guest.expires_at - timezone.now()).days >= 29


@pytest.mark.django_db
def test_authenticate_header_returns_bearer() -> None:
    drf_request = Request(APIRequestFactory().get("/"))
    assert GuestAuthentication().authenticate_header(drf_request) == "Bearer"