"""Storage tests: key shape only — no SeaweedFS needed to run pytest."""

from app.storage.s3 import key_for


def test_key_for_basic():
    assert key_for("documents", 12, "permit.pdf") == "documents/12/permit.pdf"


def test_key_for_sanitises_spaces_and_slashes():
    assert key_for("documents", 3, "My Permit /2026.pdf") == "documents/3/My_Permit_2026.pdf"


def test_key_for_accepts_string_ids():
    assert key_for("certificates", "PRM-2026-000123", "cert.pdf") == ("certificates/PRM-2026-000123/cert.pdf")


def test_key_for_empty_filename_falls_back():
    assert key_for("documents", 1, "///") == "documents/1/file"
