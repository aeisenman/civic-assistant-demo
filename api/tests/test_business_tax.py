"""The business tax rule is the one fee we compute exactly (synthesis §3)."""

from app.tools.fees import business_tax_breakdown


def test_small_tier_is_flat_base_plus_sb1186():
    result = business_tax_breakdown(5)
    # $34 base + $4 SB-1186 + 5 x $1.47 minimum wage = $45.35
    assert result["tier"] == "12 or fewer employees"
    assert result["total_usd"] == 45.35
    assert [line["amount_usd"] for line in result["line_items"]] == [34.0, 4.0, 7.35]


def test_boundary_at_twelve_employees():
    assert business_tax_breakdown(12)["tier"] == "12 or fewer employees"
    assert business_tax_breakdown(13)["tier"] == "13 or more employees"


def test_large_tier_adds_per_employee_charge():
    result = business_tax_breakdown(20)
    # $125 + 20 x $5 + $4 + 20 x $1.47 = $258.40
    assert result["total_usd"] == 258.40
    assert any("Per-employee" in line["label"] for line in result["line_items"])


def test_summary_says_estimate():
    assert "estimate" in business_tax_breakdown(3)["summary"].lower()


def test_negative_employee_count_is_clamped():
    assert business_tax_breakdown(-4)["employees"] == 0
