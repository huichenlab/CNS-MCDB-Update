import datetime as dt
import json
from pathlib import Path

from pipeline import research
from pipeline.evidence import _is_biology_relevant, _official_issue_dois
from pipeline.issues import JOURNALS, IssueCandidate, _candidate_from_items, canonical_issue_url, is_new_issue
from pipeline.qa import validate_pdf
from pipeline.report_pdf import render_report
from pipeline.research import validate_report


FIXTURE = Path(__file__).with_name("fixture_report.json")


def test_exact_journal_catalog():
    assert set(JOURNALS) == {"Science", "Nature", "Cell"}
    assert all(config["issn"] and config["current_url"].startswith("https://") for config in JOURNALS.values())


def test_canonical_issue_urls():
    assert canonical_issue_url("Science", "393", "6811") == "https://www.science.org/toc/science/393/6811"
    assert canonical_issue_url("Nature", "656", "8126") == "https://www.nature.com/nature/volumes/656/issues/8126"
    assert "X0016-X" in canonical_issue_url("Cell", "189", "16", "2026-08-06")


def test_candidate_detection_prefers_latest_nonfuture_issue():
    items = [
        {"volume": "10", "issue": "2", "published-print": {"date-parts": [[2026, 8, 6]]}},
        {"volume": "10", "issue": "3", "published-print": {"date-parts": [[2026, 8, 13]]}},
    ]
    candidate = _candidate_from_items("Nature", items, dt.date(2026, 8, 10))
    assert candidate.volume == "10"
    assert candidate.issue == "2"


def test_issue_state_comparison():
    candidate = IssueCandidate("Nature", "0028-0836", "999", "1", "2026-08-09", "https://example.test", "crossref")
    assert is_new_issue(candidate, {"issues": {}})
    assert not is_new_issue(candidate, {"issues": {"Nature": {"release_key": candidate.key}}})


def test_biology_screen():
    assert _is_biology_relevant("Chromatin regulation in stem cells", "")
    assert _is_biology_relevant("Universal cell embedding provides a foundation model for cell biology", "")
    assert not _is_biology_relevant("A quantum gate for superconducting qubits", "")
    assert not _is_biology_relevant("A thalamus-brainstem attractor network drives history-biased decisions", "Whole-brain cellular-resolution imaging in zebrafish")


def test_official_nature_doi_parser_stops_at_path_suffix():
    class Response:
        text = '<a href="/articles/s41586-026-10569-6/figures/1">A</a><a href="https://doi.org/10.1038/s41586-026-10603-7">B</a>'

        @staticmethod
        def raise_for_status():
            return None

    class Session:
        @staticmethod
        def get(*args, **kwargs):
            return Response()

    candidate = IssueCandidate("Nature", "0028-0836", "656", "8126", "2026-08-06", "https://example.test", "crossref")
    assert _official_issue_dois(candidate, Session()) == {
        "10.1038/s41586-026-10569-6",
        "10.1038/s41586-026-10603-7",
    }


def test_deterministic_research_report(monkeypatch):
    candidate = IssueCandidate(
        "Nature",
        "0028-0836",
        "999",
        "1",
        "2026-08-09",
        "https://www.nature.com/nature/volumes/999/issues/1",
        "https://api.crossref.org/journals/0028-0836/works",
    )
    packet = {
        "metadata_source": candidate.metadata_source,
        "evidence_limitations": "Abstract-only fixture.",
        "official_issue_check": {
            "verification_note": "Fixture official-page check.",
            "reachable": True,
            "identifiers_present": True,
        },
        "items": [
            {
                "title": "Chromatin signaling controls early lineage allocation",
                "authors": "A. Example, B. Example",
                "doi": "10.0000/deterministic",
                "canonical_url": "https://doi.org/10.0000/deterministic",
                "article_type": "journal-article",
                "published_date": "2026-08-09",
                "abstract": "We show that a chromatin regulator controls lineage allocation. Single-cell RNA sequencing and CRISPR perturbation reveal a directional effect.",
                "access_note": "Fixture abstract only.",
            }
        ],
    }
    monkeypatch.setattr(research, "build_evidence_packet", lambda _: packet)
    report = research.research_issue(candidate, "2026-08-10T00:00:00Z")
    validate_report(report, candidate)
    assert report["papers"][0]["source_status"] == "abstract-supported"
    assert report["papers"][0]["grant_ideas"][0]["central_hypothesis"].startswith("Speculative:")
    assert "OpenAI" in report["source_method_note"]


def test_fixture_schema_and_pdf(tmp_path):
    report = json.loads(FIXTURE.read_text())
    candidate = IssueCandidate("Nature", "0028-0836", "999", "1", dt.date.today().isoformat(), report["issue"]["canonical_issue_url"], "fixture")
    validate_report(report, candidate)
    output = tmp_path / "fixture.pdf"
    render_report(report, output)
    result = validate_pdf(output, tmp_path / "qa")
    assert result["pages"] >= 4
    assert result["bytes"] > 5_000
