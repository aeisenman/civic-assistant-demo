"""Reciprocal rank fusion is the only ranking logic we wrote, so it gets a test."""

from app.rag.retrieve import rrf, rrf_scores


def test_agreement_beats_appearing_in_one_list():
    # 2 is top in both retrievers; 1 is top in only one.
    assert rrf([[1, 2], [2]])[0] == 2


def test_a_first_place_and_a_third_place_edges_out_two_seconds():
    # With k=60 the curve is flat: 1/61 + 1/63 > 2/62. Documented, not a bug —
    # it is why RRF needs no score calibration between the two retrievers.
    assert rrf([[1, 2, 3], [3, 2, 1]])[0] == 1


def test_ids_in_one_list_only_still_rank():
    order = rrf([[10, 11], [12]])
    assert order[0] == 10  # rank 1 in its list
    assert set(order) == {10, 11, 12}


def test_scores_sum_across_lists():
    scores = rrf_scores([[7], [7]], k=60)
    assert scores[7] == 2 * (1 / 61)


def test_order_is_deterministic_on_ties():
    # Identical scores: first appearance wins, twice in a row.
    assert rrf([[1], [2]]) == rrf([[1], [2]]) == [1, 2]


def test_empty_input():
    assert rrf([[], []]) == []


async def test_a_huge_query_is_truncated_before_the_embedding_call(monkeypatch):
    """A 50 KB paste exceeded the embedding model's 8,192-token input limit and
    took the whole turn down to the generic "something went wrong" apology."""
    from app.rag import retrieve as retrieve_module

    seen: list[str] = []

    async def fake_embed(texts):
        seen.append(texts[0])
        return [[0.0, 0.0, 0.0]]

    async def fake_run(session, query, vector, topic):
        return [], []

    monkeypatch.setattr(retrieve_module, "embed", fake_embed)
    monkeypatch.setattr(retrieve_module, "_run", fake_run)

    hits = await retrieve_module.retrieve(None, "trash day at 4521 Adams Ave. " * 3000)
    assert hits == []
    assert len(seen[0]) == retrieve_module.MAX_QUERY_CHARS
