from types import SimpleNamespace

import pytest
from django.http import HttpRequest
from django.test import RequestFactory

from apps.accounts.models import GuestIdentity
from apps.matches.models import Match
from config.admin import ReadOnlyProductionAdmin


class _Admin(ReadOnlyProductionAdmin):
    model = Match


def _request(user: object = None) -> HttpRequest:
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def _make_guest() -> GuestIdentity:
    guest, _ = GuestIdentity.issue(display_name="Amir", avatar_id="avatar_01")
    return guest


@pytest.mark.django_db
def test_read_only_production_admin_forbids_add() -> None:
    assert _Admin().has_add_permission(_request(_make_guest())) is False


@pytest.mark.django_db
def test_change_permission_requires_active_staff() -> None:
    staff_admin = SimpleNamespace(is_active=True, is_staff=True)
    assert _Admin().has_change_permission(_request(staff_admin)) is True
    inactive = SimpleNamespace(is_active=False, is_staff=True)
    assert _Admin().has_change_permission(_request(inactive)) is False
    non_staff = SimpleNamespace(is_active=True, is_staff=False)
    assert _Admin().has_change_permission(_request(non_staff)) is False


@pytest.mark.django_db
def test_read_only_production_admin_forbids_delete() -> None:
    assert _Admin().has_delete_permission(_request(_make_guest())) is False


@pytest.mark.django_db
def test_read_only_fields_cover_every_model_field() -> None:
    guest = _make_guest()
    fields = _Admin().get_readonly_fields(_request(guest))
    expected = tuple(field.name for field in Match._meta.fields)
    assert tuple(fields) == expected