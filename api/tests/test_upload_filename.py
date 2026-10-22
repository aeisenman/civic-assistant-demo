"""The stored upload filename is a basename, printable and bounded.

Exercises app.api.documents.safe_filename directly — it is a pure function, so
no HTTP client and no storage are needed. Depends on: app.api.documents.
Red-team finding 20: `../../../../etc/passwd` came back out verbatim.
"""

from app.api.documents import FALLBACK_FILENAME, MAX_FILENAME_CHARS, safe_filename


def test_a_traversal_path_becomes_its_basename():
    assert safe_filename("../../../../etc/passwd") == "passwd"
    assert safe_filename("/var/tmp/permit.pdf") == "permit.pdf"
    assert safe_filename(r"C:\Users\me\Desktop\permit.pdf") == "permit.pdf"


def test_control_characters_are_stripped():
    assert safe_filename("per\x00mit\n.pdf") == "permit.pdf"
    assert safe_filename("\x1b[31mred\x1b[0m.pdf") == "[31mred[0m.pdf"


def test_an_empty_or_dotty_name_falls_back():
    for raw in (None, "", "   ", "..", "/", "\x00"):
        assert safe_filename(raw) == FALLBACK_FILENAME


def test_a_long_name_is_capped_but_keeps_its_extension():
    name = safe_filename("a" * 400 + ".pdf")
    assert len(name) == MAX_FILENAME_CHARS
    assert name.endswith(".pdf")


def test_a_long_name_with_no_usable_extension_is_just_cut():
    name = safe_filename("b" * 400)
    assert name == "b" * MAX_FILENAME_CHARS


def test_an_ordinary_name_is_left_exactly_alone():
    assert safe_filename("Permit Application (signed).pdf") == "Permit Application (signed).pdf"
