"""get_referral's word matching and ranking, and the topic list the prompts quote.

Exercises the pure halves of app/tools/civic.get_referral (there is no database in
the unit suite) plus the REFERRAL_TOPICS constant in app/agents/profiles.py, which
would silently go stale if nothing checked it against seed_data/referrals.json.
"""

import json
import pathlib
from dataclasses import dataclass

from app.agents.profiles import REFERRAL_TOPICS
from app.tools.civic import rank_referrals, referral_terms, stem

REFERRALS_JSON = pathlib.Path(__file__).resolve().parents[1] / "seed_data" / "referrals.json"


@dataclass
class Row:
    """Stands in for models.Referral: rank_referrals only reads these three fields."""

    topic: str
    agency: str
    note: str | None = ""


def test_terms_keep_the_significant_words_and_stem_them():
    """ "dog" is the whole question, so a three-letter floor; "the" is not, so a stoplist."""
    assert referral_terms("Do I need a dog license?") == ["need", "dog", "licens"]
    assert referral_terms("What are the rules for a dog?") == ["rule", "dog"]


def test_terms_are_lowercased_deduplicated_and_ordered():
    assert referral_terms("Health HEALTH permit health") == ["health", "permit"]


def test_terms_can_be_empty_for_a_query_with_nothing_in_it():
    # get_referral falls back to the raw phrase when this happens.
    assert referral_terms("dog") == ["dog"]
    assert referral_terms("!!") == []
    assert referral_terms("the and for") == []


def test_rank_puts_the_row_that_matched_more_words_first():
    rows = [
        Row("Contractor state license", "CSLB", "Contractor licensing is a State function."),
        Row("Food facility health permit", "County DEHQ", "Health permits are issued by the County."),
    ]
    ranked = rank_referrals(rows, referral_terms("restaurant health permit license"))
    assert [r.topic for r in ranked] == ["Food facility health permit", "Contractor state license"]


def test_rank_drops_rows_that_matched_nothing():
    rows = [Row("Voter registration", "Registrar", "Register to vote online.")]
    assert rank_referrals(rows, ["parking"]) == []


def test_rank_matches_the_agency_column_too():
    rows = [Row("Gas / electric utility billing", "SDG&E (private utility)", None)]
    assert rank_referrals(rows, ["sdge"]) == []  # "SDG&E" is not the token "sdge"
    assert len(rank_referrals(rows, ["utility"])) == 1


def test_rank_is_stable_for_rows_with_the_same_score():
    rows = [Row("A permit", "X", ""), Row("B permit", "Y", "")]
    assert [r.topic for r in rank_referrals(rows, ["permit"])] == ["A permit", "B permit"]


def test_the_stemmer_strips_one_suffix_and_never_below_four_letters():
    assert stem("licensing") == "licens"
    assert stem("license") == "licens"
    assert stem("licenses") == "licens"
    assert stem("permits") == "permit"
    # Four letters is the floor, so short words survive intact.
    assert stem("dog") == "dog"
    assert stem("does") == "does"
    assert stem("used") == "used"


def seed_rows() -> list[Row]:
    """The real referral table, as rank_referrals sees it."""
    return [
        Row(**{k: r[k] for k in ("topic", "agency", "note")}) for r in json.loads(REFERRALS_JSON.read_text())
    ]


def test_a_dog_licence_reaches_animal_services_and_not_the_dmv():
    """Red-team finding 9: "license" is not a substring of "licensing"."""
    for phrase in ("dog license", "dog licence", "dog licensing"):
        ranked = rank_referrals(seed_rows(), referral_terms(phrase))
        assert ranked, f"{phrase!r} matched no referral at all"
        assert ranked[0].topic == "Dog licensing", phrase
        assert "DMV" not in ranked[0].agency


def test_a_loose_animal_reaches_the_humane_society_and_not_the_licensing_row():
    """M23: the words a resident types about a live stray must not land on dog licensing.

    "Dog licensing" already matched the word "dog", so before the animal-control
    row existed a stray-dog question was answered with the licensing page. These
    are the phrasings research/08 records residents using.
    """
    for phrase in (
        "stray dog running loose on my street",
        "loose dog in my neighborhood",
        "stray cat",
        "injured animal in the road",
    ):
        ranked = rank_referrals(seed_rows(), referral_terms(phrase))
        assert ranked, f"{phrase!r} matched no referral at all"
        assert ranked[0].topic == "Stray, loose or injured animal", phrase
        assert "Humane Society" in ranked[0].agency


def test_the_dog_licence_row_survives_the_new_animal_row():
    """The new row shares the word "dog"; licensing questions must still win it."""
    for phrase in ("dog license", "dog licence", "dog licensing"):
        ranked = rank_referrals(seed_rows(), referral_terms(phrase))
        assert ranked[0].topic == "Dog licensing", phrase


def test_the_dmv_row_still_wins_its_own_question():
    ranked = rank_referrals(seed_rows(), referral_terms("driver's license renewal"))
    assert ranked[0].topic == "Vehicle registration / driver's license"


def test_three_more_phrases_reach_the_row_a_resident_meant():
    for phrase, topic in (
        ("restaurant health permits", "Food facility health permit"),
        ("registering an LLC", "Business entity registration (LLC/Corp/LP)"),
        ("RV parking at the trolley station", "Trolley/bus station parking"),
    ):
        ranked = rank_referrals(seed_rows(), referral_terms(phrase))
        assert ranked and ranked[0].topic == topic, phrase


def test_a_topic_match_outscores_a_note_only_match():
    rows = [
        Row("Something else entirely", "Agency", "Parking is mentioned only in this note."),
        Row("Trolley/bus station parking", "MTS", "A separate regional transit agency."),
    ]
    ranked = rank_referrals(rows, referral_terms("parking"))
    assert [r.topic for r in ranked] == [
        "Trolley/bus station parking",
        "Something else entirely",
    ]


async def test_a_wildcard_query_does_not_match_every_event():
    """search_events(query="%") used to ILIKE '%%%' and return the whole table."""
    from app.tools.civic import SearchEventsArgs, search_events

    seen = []

    class _Session:
        async def execute(self, statement, *args, **kwargs):
            seen.append(str(statement.compile(compile_kwargs={"literal_binds": True})))

            class _Scalars:
                def all(self):
                    return []

            return type("R", (), {"scalars": lambda self: _Scalars()})()

    await search_events(SearchEventsArgs(query="%"), _Session())
    assert "ESCAPE '\\'" in seen[0]
    assert "'%\\%%'" in seen[0]


def test_every_topic_the_prompt_advertises_is_findable_in_the_seed_file():
    """The prompt promises these words work; prove each one still matches a row."""
    rows = [
        Row(**{k: r[k] for k in ("topic", "agency", "note")}) for r in json.loads(REFERRALS_JSON.read_text())
    ]
    for advertised in REFERRAL_TOPICS.split("; "):
        terms = referral_terms(advertised)
        assert terms, f"no matchable words in advertised topic {advertised!r}"
        assert rank_referrals(rows, terms), f"advertised topic {advertised!r} matches no referral"
