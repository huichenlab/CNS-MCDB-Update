from __future__ import annotations

import concurrent.futures
import html
import re
from typing import Any

import requests

from .issues import IssueCandidate, USER_AGENT, _parts_date


EXCLUDED_TITLE_TERMS = (
    "editorial",
    "correction",
    "retraction",
    "news & views",
    "news and views",
    "perspective",
    "review",
    "book review",
    "in brief",
    "research highlight",
)

BIOLOGY_PATTERNS = (
    r"\bcells?\b", r"\bcellular\b", r"\bcell[- ]type", r"\bcell biology\b", r"\bmolecular biology\b",
    r"\bgenes?\b", r"\bgenetic", r"\bgenom", r"\bproteins?\b", r"\bpeptides?\b",
    r"\bDNA\b", r"\bRNA\b", r"\bchromatin\b", r"\bepigen", r"\btranscript",
    r"\btranslation\b", r"\bribosom", r"\bembry", r"\bdevelopmental\b", r"\bmorphogen",
    r"\btissues?\b", r"\borganoid", r"\bstem cells?\b", r"\bdifferentiat", r"\blineage",
    r"\bsignall?ing\b", r"\breceptors?\b", r"\benzymes?\b", r"\bmembrane\b",
    r"\bcytoskeleton\b", r"\borganelle", r"\bmitochond", r"\bmetabol", r"\bcancer\b",
    r"\btumou?r", r"\bimmune\b", r"\binflamm", r"\bneur", r"\bbrain\b", r"\bglia",
    r"\bbacter", r"\bviral\b", r"\bvirus\b", r"\bmicrobi", r"\bpathogen", r"\bhost cells?\b",
    r"\bhomeostasis\b", r"\bsenescence\b", r"\bageing\b", r"\baging\b", r"\bregeneration\b",
    r"\bzebrafish\b", r"\bmice\b", r"\bmouse\b", r"\bhuman blood\b", r"\bplant",
)

HIGH_SPECIFICITY_PATTERNS = (
    r"\bchromatin\b", r"\bembry", r"\borganoid", r"\bmitochond", r"\bcancer\b", r"\btumou?r",
    r"\bimmune\b", r"\bneur", r"\bzebrafish\b", r"\bstem cells?\b", r"\bCRISPR\b",
    r"\bDNA mutations?\b", r"\bsingle[- ]cell\b", r"\bcell[- ]type\b", r"\bcell biology\b", r"\btranscriptom",
)

NONBIOLOGY_TITLE_PATTERNS = (
    r"\bquantum\b", r"\bqubits?\b", r"\bsuperconduct", r"\bgraphene\b", r"\bferroelectric",
    r"\bphotonic\b", r"\bpolariton\b", r"\bperovskite\b", r"\bcopolymer", r"\bpolyesters?\b",
    r"\bcataly", r"\blactonization\b", r"\baliphatic acids?\b", r"\bMXenes?\b",
    r"\bVenus\b", r"\bCambrian\b", r"\bfossils?\b", r"\bocean iron\b",
    r"\blarge language models?\b", r"\bmedical AI\b", r"\bprivacy risks?\b",
)

OUT_OF_SCOPE_TITLE_PATTERNS = (r"\battractor network\b", r"\bhistory[- ]biased decisions\b")


def _clean_markup(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _authors(item: dict[str, Any]) -> str:
    names: list[str] = []
    for author in item.get("author") or []:
        full = " ".join(part for part in (author.get("given"), author.get("family")) if part)
        if full:
            names.append(full)
    if len(names) > 8:
        return ", ".join(names[:8]) + ", et al."
    return ", ".join(names) or "Author list unavailable in retrieved metadata"


def _official_issue_dois(candidate: IssueCandidate, session: requests.Session) -> set[str]:
    """Extract publisher DOI links from the exact issue page when accessible."""

    try:
        response = session.get(
            candidate.canonical_issue_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException:
        return set()
    html_text = html.unescape(response.text)
    patterns = {
        "Nature": (r"(?:https?://doi\.org/10\.1038/|/articles/)(s41586-\d{3}-[A-Za-z0-9-]+?)(?=[/?#\"'<>])",),
        "Science": (r"(?:https?://doi\.org/|/doi/)(10\.1126/science\.[A-Za-z0-9._-]+)",),
        "Cell": (r"(?:https?://doi\.org/|/doi/(?:full|abs)/)(10\.1016/j\.cell\.[A-Za-z0-9()._-]+)",),
    }
    dois: set[str] = set()
    for pattern in patterns[candidate.journal]:
        for match in re.findall(pattern, html_text, flags=re.IGNORECASE):
            doi = str(match).strip().rstrip("-.,;\"'<>/").lower()
            if candidate.journal == "Nature" and not doi.startswith("10.1038/"):
                doi = "10.1038/" + doi
            dois.add(doi)
    sample = ", ".join(sorted(dois)[:3])
    print(f"{candidate.journal}: extracted {len(dois)} DOI link(s) from the official issue page; sample: {sample}")
    return dois


def _matching_works(candidate: IssueCandidate, session: requests.Session) -> list[dict[str, Any]]:
    official_dois = _official_issue_dois(candidate, session)
    if official_dois:
        def resolve(doi: str) -> dict[str, Any] | None:
            try:
                response = requests.get(
                    "https://api.crossref.org/works/" + requests.utils.quote(doi, safe="/"),
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()["message"]
            except (requests.RequestException, KeyError, ValueError):
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            resolved = list(executor.map(resolve, sorted(official_dois)))
        items = [item for item in resolved if item]
        print(f"{candidate.journal}: resolved {len(items)} of {len(official_dois)} official DOI(s) through Crossref.")
    else:
        response = session.get(
            f"https://api.crossref.org/journals/{candidate.issn}/works",
            params={
                "filter": "type:journal-article",
                "rows": 500,
                "sort": "published",
                "order": "desc",
            },
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=60,
        )
        response.raise_for_status()
        items = response.json()["message"]["items"]
    matched: list[dict[str, Any]] = []
    for item in items:
        title = " ".join(item.get("title") or []).strip()
        lower = title.lower()
        doi = str(item.get("DOI") or "").lower()
        if not title or any(term in lower for term in EXCLUDED_TITLE_TERMS):
            continue
        if candidate.journal == "Nature" and not doi.startswith("10.1038/s41586-"):
            continue
        if official_dois:
            if doi not in official_dois:
                continue
        else:
            if str(item.get("volume") or "").strip() != candidate.volume:
                continue
            if str(item.get("issue") or "").strip() != candidate.issue:
                continue
        matched.append(item)
    return matched[:150]


def _europe_pmc_abstract(doi: str, session: requests.Session) -> tuple[str, str]:
    if not doi:
        return "", ""
    try:
        response = session.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": f'DOI:"{doi}"', "format": "json", "pageSize": 1, "resultType": "core"},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
        results = response.json().get("resultList", {}).get("result", [])
        if not results:
            return "", ""
        record = results[0]
        return _clean_markup(str(record.get("abstractText") or "")), str(record.get("pmid") or record.get("pmcid") or "")
    except (requests.RequestException, ValueError):
        return "", ""


def _official_issue_check(candidate: IssueCandidate) -> dict[str, Any]:
    try:
        response = requests.get(
            candidate.canonical_issue_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=30,
            allow_redirects=True,
        )
        reachable = response.ok
        text = _clean_markup(response.text[:250_000]) if reachable else ""
        identifiers_present = candidate.volume in text and candidate.issue in text
        return {
            "url": candidate.canonical_issue_url,
            "http_status": response.status_code,
            "reachable": reachable,
            "identifiers_present": identifiers_present,
            "verification_note": (
                "Official publisher issue page was reachable and contained the detected volume and issue identifiers."
                if reachable and identifiers_present
                else "Official publisher issue page was reachable, but automated text matching did not confirm both identifiers."
                if reachable
                else f"Official publisher issue page returned HTTP {response.status_code}; no full-page review is claimed."
            ),
        }
    except requests.RequestException as exc:
        return {
            "url": candidate.canonical_issue_url,
            "http_status": None,
            "reachable": False,
            "identifiers_present": False,
            "verification_note": f"Official publisher issue page could not be retrieved ({type(exc).__name__}); no full-page review is claimed.",
        }


def _is_biology_relevant(title: str, abstract: str) -> bool:
    evidence = f"{title} {abstract}"
    if any(re.search(pattern, title, flags=re.IGNORECASE) for pattern in OUT_OF_SCOPE_TITLE_PATTERNS):
        return False
    biology_hits = sum(bool(re.search(pattern, evidence, flags=re.IGNORECASE)) for pattern in BIOLOGY_PATTERNS)
    high_specificity = any(re.search(pattern, evidence, flags=re.IGNORECASE) for pattern in HIGH_SPECIFICITY_PATTERNS)
    nonbiology_title = any(re.search(pattern, title, flags=re.IGNORECASE) for pattern in NONBIOLOGY_TITLE_PATTERNS)
    if nonbiology_title:
        return biology_hits >= 4 and high_specificity
    return high_specificity or biology_hits >= 2


def build_evidence_packet(candidate: IssueCandidate) -> dict[str, Any]:
    """Collect source-bounded public evidence without any model or paid API."""

    session = requests.Session()
    works = _matching_works(candidate, session)

    def enrich(item: dict[str, Any]) -> dict[str, Any] | None:
        doi = str(item.get("DOI") or "").strip()
        crossref_abstract = _clean_markup(str(item.get("abstract") or ""))
        epmc_abstract, pmid = ("", "") if crossref_abstract else _europe_pmc_abstract(doi, requests.Session())
        abstract = crossref_abstract or epmc_abstract
        title = " ".join(item.get("title") or []).strip()
        if not _is_biology_relevant(title, abstract):
            return None
        published = _parts_date(item)
        return {
            "title": title,
            "authors": _authors(item),
            "doi": doi,
            "canonical_url": str(item.get("URL") or (f"https://doi.org/{doi}" if doi else "")),
            "publisher": str(item.get("publisher") or ""),
            "article_type": str(item.get("subtype") or item.get("type") or "journal-article"),
            "published_date": published.isoformat() if published else candidate.issue_date,
            "abstract": abstract[:8000],
            "europe_pmc_id": pmid,
            "access_note": (
                "Publisher-deposited abstract retrieved through Crossref; no full-text review is claimed."
                if crossref_abstract
                else "Abstract retrieved from Europe PMC; no full-text review is claimed."
                if epmc_abstract
                else "Metadata and title only; no abstract or full text was retrieved."
            ),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        enriched = list(executor.map(enrich, works))
    papers = [paper for paper in enriched if paper and paper.get("doi")]
    return {
        "journal": candidate.journal,
        "volume": candidate.volume,
        "issue": candidate.issue,
        "release_date": candidate.issue_date,
        "canonical_issue_url": candidate.canonical_issue_url,
        "metadata_source": candidate.metadata_source,
        "official_issue_check": _official_issue_check(candidate),
        "evidence_limitations": (
            "The automated evidence boundary is publisher-deposited Crossref metadata plus legally available Europe PMC abstracts. "
            "Publisher pages are probed but paywalls and access controls are not bypassed. Figures and full methods are not claimed as reviewed."
        ),
        "items": papers,
    }
