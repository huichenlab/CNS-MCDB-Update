from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .evidence import build_evidence_packet
from .issues import IssueCandidate


REQUIRED_PAPER_FIELDS = {
    "title", "authors", "journal", "volume", "issue", "publication_date", "article_type", "doi",
    "canonical_url", "access_note", "main_discovery", "importance_implication", "methods",
    "key_evidence", "limitations", "source_status", "grant_ideas",
}

REQUIRED_GRANT_FIELDS = {
    "working_title", "importance", "knowledge_gap", "rationale_xenopus_advantage",
    "central_hypothesis", "experimental_design", "expected_results_interpretations",
    "potential_pitfalls", "alternative_strategies", "preliminary_evidence_plan", "novelty",
    "feasibility", "risk", "grant_fit", "reviewer_premise", "supporting_sources",
}

RESULT_VERBS = (
    "show", "shows", "shown", "reveal", "reveals", "identify", "identifies", "demonstrate",
    "demonstrates", "find", "finds", "found", "discover", "discovers", "establish", "uncovers",
    "report", "reports", "mediate", "mediates", "drives", "controls", "promotes", "restricts",
)

METHOD_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Single-cell transcriptomics", ("single-cell rna", "single cell rna", "scrna", "single-cell transcript")),
    ("Single-nucleus multi-omics", ("single-nucleus", "single nucleus", "snrna", "multi-omic")),
    ("Spatial transcriptomics", ("spatial transcript", "spatial omic")),
    ("CRISPR genome editing", ("crispr", "cas9", "cas12")),
    ("Live-cell or intravital imaging", ("live imaging", "live-cell", "intravital", "time-lapse")),
    ("Cryo-electron microscopy", ("cryo-em", "cryo electron")),
    ("Electron microscopy", ("electron microscopy", "tomography")),
    ("Proteomics or mass spectrometry", ("proteomic", "mass spectrom")),
    ("Chromatin profiling", ("chip-seq", "atac-seq", "chromatin accessibility", "cut&run", "cut and run")),
    ("Genome-wide association or QTL mapping", ("genome-wide association", "gwas", "quantitative trait", "eqtl")),
    ("Organoid or stem-cell model", ("organoid", "stem cell", "pluripotent")),
    ("Genetic perturbation and rescue", ("knockout", "knockdown", "mutant", "rescue", "perturb")),
    ("Biochemical reconstitution", ("reconstitut", "biochemical", "in vitro")),
    ("Quantitative imaging", ("imaging", "microscopy", "fluorescen")),
    ("Computational modeling", ("modeling", "modelling", "simulation", "machine learning")),
)

THEMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gene regulation and chromatin", ("chromatin", "transcription", "epigen", "enhancer", "genome", "rna", "gene")),
    ("cell signaling and fate control", ("signal", "receptor", "kinase", "ligand", "pathway", "fate", "differentiation")),
    ("cell mechanics and morphogenesis", ("mechan", "cytoskeleton", "migration", "adhesion", "morphogen", "tissue", "polarity")),
    ("metabolism and organelle function", ("metabol", "mitochond", "organelle", "lysosome", "autophagy", "nutrient")),
    ("cell-cycle and genome integrity", ("cell cycle", "replication", "dna repair", "mitosis", "chromosome")),
    ("neural development and function", ("neural", "neuron", "brain", "axon", "synap")),
    ("immunity and host response", ("immune", "inflamm", "host", "pathogen", "virus", "bacter")),
)


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", compact) if len(part.strip()) > 25]


def _result_sentence(abstract: str, title: str) -> str:
    sentences = _sentences(abstract)
    for sentence in sentences:
        lower = sentence.lower()
        if any(re.search(rf"\b{re.escape(verb)}\b", lower) for verb in RESULT_VERBS):
            return sentence
    if sentences:
        return sentences[-1]
    return f"The title and publisher metadata identify a primary-research study of {title.rstrip('.')}; no abstract was retrieved, so no more specific discovery claim is made."


def _importance_sentence(abstract: str, title: str) -> str:
    sentences = _sentences(abstract)
    for sentence in reversed(sentences):
        lower = sentence.lower()
        if any(term in lower for term in ("provide", "suggest", "implication", "potential", "advance", "framework", "understand")):
            return sentence
    return f"The study advances mechanistic understanding of {title.rstrip('.')} and creates a defined basis for testing conservation and developmental function in a vertebrate embryo."


def _methods(text: str) -> list[str]:
    lower = text.lower()
    found = [label for label, terms in METHOD_PATTERNS if any(term in lower for term in terms)]
    return found[:6] or ["Publisher-deposited title/abstract analysis; consult the linked paper for complete technical details"]


def _theme(text: str) -> str:
    lower = text.lower()
    scored = [(sum(lower.count(term) for term in terms), label) for label, terms in THEMES]
    score, label = max(scored)
    return label if score else "developmental conservation and mechanism"


def _topic(title: str, limit: int = 82) -> str:
    compact = re.sub(r"\s+", " ", title).strip().rstrip(".")
    return compact if len(compact) <= limit else compact[: limit - 1].rsplit(" ", 1)[0] + "..."


def _stage_profile(theme: str) -> dict[str, str]:
    if theme == "neural development and function":
        return {
            "window": "stages 10-18",
            "tissue": "neural plate and neural-border lineages",
            "primary": "neural-domain geometry, lineage allocation, and reporter dynamics",
            "secondary": "marker expression, cell trajectories, and neural-tube morphology",
        }
    if theme == "cell mechanics and morphogenesis":
        return {
            "window": "stages 10-13",
            "tissue": "dorsal mesoderm and involuting marginal-zone explants",
            "primary": "cell polarity, convergence-extension, tissue strain, and migration persistence",
            "secondary": "fate markers, adhesion dynamics, and whole-embryo axis elongation",
        }
    if theme == "metabolism and organelle function":
        return {
            "window": "stages 8-13",
            "tissue": "animal-cap and marginal-zone explants",
            "primary": "organelle state, metabolite-sensitive reporters, and lineage-marker induction",
            "secondary": "survival, developmental timing, and gastrulation morphology",
        }
    if theme == "immunity and host response":
        return {
            "window": "stages 8-18",
            "tissue": "epidermal and mesendodermal lineages before mature immunity",
            "primary": "cell-stress signaling, epithelial integrity, and lineage-specific transcription",
            "secondary": "survival, barrier morphology, and developmental timing",
        }
    return {
        "window": "stages 8-14",
        "tissue": "animal-cap, organizer, and mesendodermal lineages",
        "primary": "pathway activity, lineage allocation, and spatial marker-domain size",
        "secondary": "cell behavior, developmental timing, and gastrulation morphology",
    }


def _grant_idea(item: dict[str, Any], theme: str) -> dict[str, Any]:
    title = str(item["title"])
    topic = _topic(title)
    profile = _stage_profile(theme)
    focal = "the focal regulator or mechanism described by the featured paper"
    return {
        "working_title": f"Developmental timing and tissue autonomy of {topic}",
        "importance": (
            f"{theme.title()} is central to how embryonic cells convert molecular state into reproducible tissue organization. "
            "Establishing whether the featured mechanism operates during early vertebrate development could reveal a conserved control point and a tractable route to explain developmental variability without overstating clinical translation."
        ),
        "knowledge_gap": (
            f"The featured paper does not establish whether {focal} acts during early vertebrate development, whether its effect is cell-autonomous, which developmental window is sensitive, or whether molecular and morphogenetic phenotypes can be rescued independently."
        ),
        "rationale_xenopus_advantage": (
            "The paper supplies a candidate mechanism, while early Xenopus provides rapid external development, targeted blastomere injection, explants, lineage tracing, live imaging, inexpensive biological replication across clutches, and direct comparison of molecular and tissue-scale outcomes."
        ),
        "central_hypothesis": (
            f"Speculative: {focal} acts cell-autonomously during {profile['window']} to stabilize {profile['primary']}; acute loss will reduce the predicted molecular readout and increase pattern variance, while stage-matched wild-type rescue will restore both."
        ),
        "experimental_design": (
            f"Use Xenopus tropicalis for F0 genetics and Xenopus laevis explants. Target {profile['tissue']} by injecting two independent CRISPR RNPs at the 4- to 8-cell stage with a fluorescent lineage tracer; analyze {profile['window']}. "
            "Groups: uninjected, non-targeting RNP, each guide alone, pooled guides, dose series, wild-type mRNA rescue, perturbation-resistant rescue, and temporally delayed perturbation where a validated small molecule or inducible construct exists. "
            f"Primary readouts: {profile['primary']}. Secondary readouts: {profile['secondary']}, amplicon sequencing, RT-qPCR or in situ hybridization, and an orthogonal biochemical or reporter assay. "
            "Use at least three independent spawnings, 20-30 embryos per group per spawning for morphology, and 8-10 pooled or individually profiled samples per molecular condition; randomize embryos, blind image scoring, and analyze clutch as a random effect with multiplicity-controlled planned contrasts. "
            "Decision point: advance to epistasis and spatial single-cell profiling only if both guides reproduce the effect and rescue restores at least 50% of the molecular and developmental phenotype."
        ),
        "expected_results_interpretations": (
            "Support would be a guide-concordant loss of the predicted molecular readout, increased spatial or embryo-to-embryo variance, and rescue of both molecular and tissue phenotypes. This would place the mechanism upstream of developmental robustness. "
            "A molecular phenotype without morphogenesis would suggest buffering or a parallel tissue effector and would redirect the next aim to sensitized or explant conditions. A morphogenetic phenotype without the predicted reporter change would argue for an alternative biochemical function. "
            "No reproducible phenotype after confirmed editing would refute an obligate early role and shift the model toward redundancy, later function, or species-specific deployment."
        ),
        "potential_pitfalls": [
            "F0 mosaicism may weaken or spatially blur phenotypes.",
            "Paralog redundancy or maternal stores may mask an early requirement.",
            "High-dose perturbation may cause nonspecific toxicity or developmental delay.",
            "The featured mechanism may not be conserved or may use different effectors in amphibians.",
            "Abstract-only evidence may omit critical context needed to choose the most specific assay.",
        ],
        "alternative_strategies": [
            "Map editing per embryo and enrich analysis for high-editing specimens; establish stable alleles if mosaicism remains limiting.",
            "Target expressed paralogs jointly, use maternal-zygotic strategies where feasible, or test dominant-negative and degron-based acute perturbations.",
            "Use lower doses, later induction, tissue-restricted injection, explants, and matched survival/staging controls to separate mechanism from toxicity.",
            "Test Xenopus laevis and X. tropicalis orthologs, then validate the key interaction biochemically or in a complementary cell model.",
            "Before full-scale work, manually review the linked paper's figures and methods and revise the reporter or perturbation to match the demonstrated mechanism.",
        ],
        "preliminary_evidence_plan": (
            "Published enabling evidence and proposed preliminary-data plan: no unpublished user-laboratory data are assumed. The featured paper is the cited cross-species enabling source; direct Xenopus evidence was not automatically verified. "
            "Pilot 1: map candidate expression or pathway activity at 5-6 early stages using RT-qPCR and in situ hybridization (three spawnings; expected Figure 1A-B); go if a reproducible spatial or temporal signal exceeds twofold over the lowest stage. "
            "Pilot 2: test two CRISPR RNPs plus non-targeting control in three spawnings with at least 25 embryos per group, amplicon sequencing, blinded morphology, and the primary molecular readout (Figure 1C-E); go if both guides produce the same directional effect of at least 20% with acceptable survival. "
            "Pilot 3: perform wild-type mRNA rescue in three spawnings with at least 20 embryos per group (Figure 1F-G); go if rescue reverses at least 50% of the molecular and phenotype effect. Failure at any threshold triggers the paired alternative strategy rather than a claim of preliminary support."
        ),
        "novelty": "medium-high - transfers a recent mechanism into a spatially and temporally tractable vertebrate embryo",
        "feasibility": "high for the pilots - injection, explants, imaging, genotyping, and rescue are routine Xenopus capabilities",
        "risk": "medium - conservation, maternal contribution, and mosaicism are explicit decision points",
        "grant_fit": "Exploratory Aim 1 for conservation and causality; successful pilots support Aim 2 epistasis and Aim 3 spatial mechanism.",
        "reviewer_premise": "Xenopus can test when, where, and whether a newly reported cellular mechanism controls intact vertebrate development in one experimentally integrated system.",
        "supporting_sources": [
            {
                "citation": "Featured paper (publisher-linked source)",
                "doi_or_pmid": item["doi"],
                "url": item["canonical_url"],
                "evidence_type": "featured paper",
            }
        ],
    }


def _paper_record(candidate: IssueCandidate, item: dict[str, Any]) -> dict[str, Any]:
    title = str(item["title"])
    abstract = str(item.get("abstract") or "")
    combined = f"{title}. {abstract}"
    sentences = _sentences(abstract)
    evidence = [sentence for sentence in sentences if any(verb in sentence.lower() for verb in RESULT_VERBS)][:3]
    if not evidence:
        evidence = [
            "The retrieved publisher-deposited metadata identifies this item as a journal article in the detected volume and issue.",
            "The DOI provides the canonical path for manual verification of figures and full methods.",
        ]
    theme = _theme(combined)
    return {
        "title": title,
        "authors": item["authors"],
        "journal": candidate.journal,
        "volume": candidate.volume,
        "issue": candidate.issue,
        "publication_date": item.get("published_date") or candidate.issue_date,
        "article_type": item.get("article_type") or "journal-article",
        "doi": item["doi"],
        "canonical_url": item["canonical_url"],
        "access_note": item["access_note"],
        "main_discovery": _result_sentence(abstract, title),
        "importance_implication": _importance_sentence(abstract, title),
        "methods": _methods(combined),
        "key_evidence": evidence,
        "limitations": [
            "This automated report used title, DOI metadata, and an available abstract; it does not claim manual full-text, figure, or complete methods review.",
            "The deterministic extractor cannot assess experimental quality, effect size, statistics, or unreported negative results beyond the retrieved source text.",
            "The proposed Xenopus mechanism is new speculation and has not been established by the featured paper.",
        ],
        "source_status": "abstract-supported" if abstract else "metadata/title-supported",
        "grant_ideas": [_grant_idea(item, theme)],
        "theme": theme,
    }


def _synthesis(papers: list[dict[str, Any]]) -> dict[str, Any]:
    themes = Counter(str(paper.get("theme") or "developmental conservation and mechanism") for paper in papers)
    methods = Counter(method for paper in papers for method in paper.get("methods") or [])
    ranked: list[dict[str, Any]] = []
    for rank, paper in enumerate(papers[:4], start=1):
        idea = paper["grant_ideas"][0]
        ranked.append({
            "rank": rank,
            "title": idea["working_title"],
            "source_papers": [paper["title"]],
            "significance": "high if the focal mechanism is conserved",
            "novelty": "medium-high",
            "mechanistic_clarity": "medium pending candidate-specific assay refinement",
            "preliminary_support": "featured-paper evidence; Xenopus pilots proposed",
            "xenopus_advantage": "high for temporal, spatial, rescue, and explant experiments",
            "feasibility": "high for the three rapid pilots",
            "follow_on_aims": "epistasis, spatial profiling, and cross-species validation",
        })
    dominant = themes.most_common(1)[0][0] if themes else "developmental conservation and mechanism"
    coherent = (
        f"A coherent multi-aim proposal can unite papers centered on {dominant}: Aim 1 establishes conservation and timing, "
        "Aim 2 resolves cell autonomy and pathway order, and Aim 3 links molecular activity to tissue-scale robustness."
        if len(papers) >= 2
        else "The single strongest concept is best positioned as an exploratory pilot until a second mechanistically connected paper or direct Xenopus dataset supports a multi-aim structure."
    )
    return {
        "recurring_mechanisms": [f"{name} ({count} paper{'s' if count != 1 else ''})" for name, count in themes.most_common(5)],
        "methodological_trends": [f"{name} ({count})" for name, count in methods.most_common(6)],
        "ranked_opportunities": ranked,
        "why_xenopus_now": (
            "Early Xenopus combines rapid external development, targeted microinjection, explants, lineage tracing, live imaging, F0 CRISPR, rescue, and scalable replication. It can convert abstract-supported candidate mechanisms into spatially resolved causal tests before committing to slower mammalian models."
        ),
        "coherent_multi_aim_proposal": coherent,
        "independent_pilots": [paper["grant_ideas"][0]["working_title"] for paper in papers[1:4]],
    }


def validate_report(report: dict[str, Any], candidate: IssueCandidate) -> None:
    issue = report.get("issue") or {}
    if str(issue.get("journal")) != candidate.journal:
        raise ValueError("Report journal does not match the detected candidate")
    if not report.get("papers"):
        raise ValueError("No relevant primary-research papers were identified")
    for index, paper in enumerate(report["papers"], start=1):
        missing = REQUIRED_PAPER_FIELDS - set(paper)
        if missing:
            raise ValueError(f"Paper {index} missing fields: {sorted(missing)}")
        if not paper.get("doi") or not paper.get("canonical_url"):
            raise ValueError(f"Paper {index} lacks DOI or canonical URL")
        if not (1 <= len(paper.get("grant_ideas") or []) <= 3):
            raise ValueError(f"Paper {index} must contain 1-3 grant ideas")
        for idea_index, idea in enumerate(paper["grant_ideas"], start=1):
            missing_idea = REQUIRED_GRANT_FIELDS - set(idea)
            if missing_idea:
                raise ValueError(f"Paper {index} idea {idea_index} missing fields: {sorted(missing_idea)}")


def research_issue(candidate: IssueCandidate, retrieved_at: str) -> dict[str, Any]:
    packet = build_evidence_packet(candidate)
    papers = [_paper_record(candidate, item) for item in packet.get("items") or []]
    if not papers:
        raise RuntimeError("No cellular, molecular, or developmental biology papers were identified from retrieved issue metadata")
    issue_check = packet["official_issue_check"]
    report = {
        "issue": {
            "journal": candidate.journal,
            "volume": candidate.volume,
            "issue": candidate.issue,
            "issue_date": candidate.issue_date,
            "canonical_issue_url": candidate.canonical_issue_url,
            "retrieved_at": retrieved_at,
        },
        "screening_notes": [
            issue_check["verification_note"],
            f"Screened {len(packet.get('items') or [])} biology-relevant journal articles after excluding reviews, perspectives, news, corrections, and editorials by metadata/title rules.",
            "All summaries are deterministic extractions from the bounded public evidence packet; no language-model API or paid research service was used.",
        ],
        "papers": papers,
        "cross_paper_synthesis": _synthesis(papers),
        "source_method_note": (
            f"Retrieved {retrieved_at}. Change detection and bibliographic metadata: publisher-deposited Crossref record ({packet['metadata_source']}). "
            "Abstract fallback: Europe PMC when available. Canonical issue and DOI URLs point to the publishers. "
            f"Official-page check: {issue_check['verification_note']} {packet['evidence_limitations']} "
            "No OpenAI API, model API, paid literature service, paywall bypass, unpublished user data, or claimed full-text review was used. "
            "Grant concepts are speculative templates requiring expert, candidate-specific revision."
        ),
    }
    validate_report(report, candidate)
    return report
