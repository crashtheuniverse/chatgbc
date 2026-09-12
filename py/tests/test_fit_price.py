"""py/fit.py's price model against the v0.9 census.

price() is what v1.0's shape planning reads, and every term in it is a
count from a kernel's listing. This holds the sum to the measured token:
the 8-token census of the shipped shape (fit.CENSUS_V09, staged 973,032
cycles) within 3%, and each of the large stages within 5%, so a kernel that
changes without its term being recalibrated fails here, not in a plan.
"""
import pytest

fit = pytest.importorskip("fit")


def test_price_matches_the_census_at_the_shipped_shape():
    st = fit.price_stages(**fit.SHIPPED)
    assert set(st) == set(fit.CENSUS_V09), (set(st) ^ set(fit.CENSUS_V09))
    total, measured = sum(st.values()), sum(fit.CENSUS_V09.values())
    assert abs(total / measured - 1) < 0.03, (total, measured)
    assert fit.price(**fit.SHIPPED) == total
    for name, m in fit.CENSUS_V09.items():
        if m >= 20_000:
            assert abs(st[name] / m - 1) < 0.05, (name, st[name], m)


def test_price_scales_with_the_shape():
    base = fit.price(**fit.SHIPPED)
    assert fit.price(4, 64, 176, 1024) > base
    assert fit.price(3, 96, 176, 1024) > base
    assert fit.price(3, 64, 256, 1024) > base
    assert fit.price(3, 64, 176, 2048) > base
    # A layer costs what the census says a layer costs: the token less the
    # classifier, the final norm and the embedding, over three.
    per_layer = fit.price(4, 64, 176, 1024) - base
    assert 200_000 < per_layer < 250_000, per_layer
