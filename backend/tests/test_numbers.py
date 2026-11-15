from app.explain.numbers import allowed_numbers, extract_numbers, find_match


def test_allowed_numbers_reads_figures():
    report = {"variables": [], "figures": [0.42, 17, None, float("nan"), True, "x"]}
    allowed = allowed_numbers(report)
    figures = [a for a in allowed if a.origin.startswith("figure[")]
    assert [(a.value, a.percent, a.origin) for a in figures] == [(0.42, False, "figure[0]"), (17.0, False, "figure[1]")]
    assert find_match(extract_numbers("about 0.42")[0], allowed) is not None
    assert find_match(extract_numbers("17 years")[0], allowed) is not None
    assert find_match(extract_numbers("99 years")[0], allowed) is None
    assert find_match(extract_numbers("17%")[0], allowed) is None  # plain figures stay plain
