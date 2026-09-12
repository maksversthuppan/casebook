"""Portal-text comparison helpers - no live page involved.

A real case (2026-09-12): the ingestion wizard rejected a court selection as
"did not take" even though the option text and the field's read-back value
looked identical once rendered - internal whitespace the portal's own markup
and the input disagreed on, invisible once a browser (or our own error
message) collapses it for display.
"""

from app.dcms.portal import _normalize_ws


def test_normalize_ws_collapses_internal_runs():
    assert _normalize_ws("JFMC  4 Attingal") == _normalize_ws("JFMC 4 Attingal")


def test_normalize_ws_leaves_single_spaces_alone():
    assert _normalize_ws("JFMC 4 Attingal") == "JFMC 4 Attingal"


def test_normalize_ws_treats_tabs_and_newlines_as_whitespace_too():
    assert _normalize_ws("JFMC\t4\nAttingal") == _normalize_ws("JFMC 4 Attingal")


def test_normalize_ws_does_not_hide_a_real_difference():
    assert _normalize_ws("JFMC 4 Attingal") != _normalize_ws("JFMC 5 Attingal")
