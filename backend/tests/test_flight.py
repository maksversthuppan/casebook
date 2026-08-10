"""The parser, run against real captures.

Fixtures are raw DCMS responses saved verbatim from `dcms_snapshots.raw_response`
- see `app/dcms/flight.py` for which searches produced them.
"""

import datetime as dt
from pathlib import Path

from app.dcms.flight import (
    extract_case,
    extract_case_detail,
    extract_cases,
    join_responses,
    parse_flight,
    split_responses,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestParseFlight:
    def test_splits_numbered_chunks(self):
        parsed = parse_flight(_load("dcms_case_found.txt"))
        assert set(parsed["chunks"]) == {"0", "1"}
        assert parsed["undecoded"] == []

    def test_chunk_zero_is_a_promise_to_chunk_one(self):
        parsed = parse_flight(_load("dcms_case_found.txt"))
        assert parsed["chunks"]["0"][0] == "$@1"


class TestExtractCase:
    def test_reads_a_found_case(self):
        case = extract_case(parse_flight(_load("dcms_case_found.txt")))

        assert case is not None
        assert case.cino == "KLTV080027432025"
        assert case.case_type == "MC"
        assert case.registration_number == "202502000582025"
        assert case.filing_number == "203102046352025"
        assert case.court_status == "Pending"
        assert case.subject == "Protection of Women from Domestic Violence"

    def test_reads_filing_and_registration_dates(self):
        case = extract_case(parse_flight(_load("dcms_case_found.txt")))
        assert case.registration_date == dt.date(2025, 5, 29)
        assert case.filing_date == dt.date(2025, 5, 29)

    def test_reads_both_parties(self):
        case = extract_case(parse_flight(_load("dcms_case_found.txt")))

        assert case.petitioner.name == "Rekha Devi P S and 2 Others"
        assert case.petitioner.advocate_name == "SANDHYA S"
        assert case.petitioner.advocate_registration == "K/786/2005"

        assert case.respondent.name == "BINU S L and ANOTHER"
        assert case.respondent.advocate_registration == "K/000805/2017"

    def test_reads_the_individuals_the_lead_names_stand_in_for(self):
        """"Rekha Devi P S and 2 Others" / "BINU S L and ANOTHER" are cause-
        title labels, not the whole story - `adlData` enumerates who they
        stand in for, previously read by nothing here at all."""
        case = extract_case(parse_flight(_load("dcms_case_found.txt")))

        assert [p.name for p in case.petitioner_others] == ["Diya R Binu", "Nila R Binu"]
        assert [p.party_no for p in case.petitioner_others] == [1, 2]
        assert case.petitioner_others[0].advocate_name == "SANDHYA S"

        assert [p.name for p in case.respondent_others] == ["Leela R"]
        assert case.respondent_others[0].party_no == 3

        assert case.petitioner.party_no == 0
        assert case.respondent.party_no == 0

    def test_dates_are_converted_from_utc_midnight_to_ist(self):
        """`T18:30:00.000Z` is IST midnight, not the UTC calendar date."""
        case = extract_case(parse_flight(_load("dcms_case_found.txt")))

        assert case.first_hearing == dt.date(2025, 5, 29)
        assert case.next_hearing == dt.date(2026, 10, 1)
        assert case.last_hearing == dt.date(2026, 8, 7)

    def test_a_search_that_matched_nothing_reads_as_no_case(self):
        case = extract_case(parse_flight(_load("dcms_case_not_found.txt")))
        assert case is None


class TestExtractCases:
    """Every step from a response to a Case takes one element of a list, so
    that the Advocate Name tab - one CAPTCHA, every case an advocate is on -
    needs no rewrite of the parser when phase 2 reaches it."""

    def test_the_one_result_tabs_yield_a_single_case(self):
        cases = extract_cases(parse_flight(_load("dcms_case_found.txt")))
        assert len(cases) == 1
        assert cases[0].cino == "KLTV080027432025"

    def test_the_duplicate_type_1_and_type_2_rows_are_one_case(self):
        """`data` carries this case twice, differing only in a `type` field
        whose meaning is still an open question. Two rows, one case."""
        parsed = parse_flight(_load("dcms_case_found.txt"))
        rows = parsed["chunks"]["1"]["data"]
        assert len(rows) == 2
        assert {r["cino"] for r in rows} == {"KLTV080027432025"}
        assert len(extract_cases(parsed)) == 1

    def test_matching_nothing_is_an_empty_list_not_an_error(self):
        assert extract_cases(parse_flight(_load("dcms_case_not_found.txt"))) == []

    def test_extract_case_is_the_single_result_form(self):
        parsed = parse_flight(_load("dcms_case_found.txt"))
        assert extract_case(parsed) == extract_cases(parsed)[0]


class TestMultipleResponses:
    """A found case's detail view arrives as several Server Action responses,
    not one - `portal.submit()` now captures all of them (see ROADMAP.md,
    2026-08-09). `dcms_case_detail_burst.txt` is nine real responses for one
    case, joined exactly as `join_responses` would - case history, acts &
    section, crime details, additional party rows and order metadata.
    """

    def test_split_responses_recovers_every_response(self):
        raw = _load("dcms_case_detail_burst.txt")
        responses = split_responses(raw)
        assert len(responses) == 9

    def test_join_then_split_round_trips(self):
        raw = _load("dcms_case_detail_burst.txt")
        responses = split_responses(raw)
        assert join_responses(responses) == raw

    def test_extract_case_still_reads_only_the_first_response(self):
        """The rest of the burst must not confuse the existing parser."""
        raw = _load("dcms_case_detail_burst.txt")
        first = split_responses(raw)[0]
        case = extract_case(parse_flight(first))

        assert case is not None
        assert case.cino == "KLTV080027432025"


class TestExtractCaseDetail:
    """The other nine responses, classified by shape and read in full."""

    def _detail(self):
        return extract_case_detail(split_responses(_load("dcms_case_detail_burst.txt")))

    def test_reads_the_full_hearing_history(self):
        detail = self._detail()
        assert len(detail.hearings) == 10
        assert [h.date for h in detail.hearings] == sorted(h.date for h in detail.hearings)

        first, last = detail.hearings[0], detail.hearings[-1]
        assert first.date == dt.date(2025, 5, 29)
        assert first.presiding_officer == "Smt.Elsa Catherine George"
        assert "Taken on file as MC 58/2025" in first.outcome

        assert last.date == dt.date(2026, 8, 7)
        assert last.presiding_officer == "Mithun Gopi G S"
        assert last.next_date == dt.date(2026, 10, 1)

    def test_reads_acts_and_section(self):
        detail = self._detail()
        assert len(detail.act_sections) == 1
        act = detail.act_sections[0]
        assert act.name == "Protection of Women from Domestic Violence Rules"
        assert act.section == "12"

    def test_reads_crime_details_even_when_mostly_empty(self):
        """This case has no real FIR - only the police station is on record,
        which is still worth keeping (see flight.py, extract_case_detail)."""
        detail = self._detail()
        assert detail.crime_details is not None
        assert detail.crime_details.police_station == "Thiruvananthapuram City Medical College PS"
        assert detail.crime_details.fir_no is None
        assert detail.crime_details.fir_year is None

    def test_reads_counsel_by_individual_party_deduplicated(self):
        """Keyed by (type, party_no), not just side - counsel is per
        individual, confirmed by this response carrying party_no at all."""
        detail = self._detail()
        assert detail.counsel_for(1, 0) == []  # no petitioner-side history in this burst

        lead_names = {c.name for c in detail.counsel_for(2, 0)}  # "BINU S L and ANOTHER"
        other_names = {c.name for c in detail.counsel_for(2, 3)}  # "Leela R"
        assert lead_names == {"AJITH R", "ASHEER A K"}
        assert other_names == {"AJITH R", "ASHEER A K"}

    def test_reads_order_dates(self):
        detail = self._detail()
        assert detail.order_dates == [dt.date(2025, 5, 29)]

    def test_a_burst_with_only_the_main_response_reads_as_empty(self):
        detail = extract_case_detail([_load("dcms_case_found.txt")])
        assert detail.hearings == []
        assert detail.act_sections == []
        assert detail.crime_details is None
        assert detail.counsel_for(1, 0) == []
        assert detail.order_dates == []

    def test_which_shapes_arrived_is_recorded_apart_from_what_was_in_them(self):
        """Saying nothing and saying none are different answers, and only one
        of them may clear a Case's Act & Section list (ADR-0007)."""
        assert self._detail().kinds_seen == {
            "hearings",
            "acts",
            "crime",
            "counsel",
            "orders",
        }
        thin = extract_case_detail([_load("dcms_case_found.txt")])
        assert thin.kinds_seen == frozenset()
        assert thin.reported("acts") is False
