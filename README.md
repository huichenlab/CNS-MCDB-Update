# CNS MCDB Update

Private, repository-native monitoring for the newest issues of **Cell**, **Nature**, and **Science**. The workflow detects a newly released issue, screens publisher-deposited metadata and legally accessible abstracts for cellular, molecular, or developmental biology, builds a landscape infographic PDF with early-*Xenopus* proposal panels, validates every PDF page, and commits the finished PDF and evidence report directly to this repository.

## Zero-OpenAI design

This repository:

- does **not** call the OpenAI API;
- does **not** read `OPENAI_API_KEY` or any other model key;
- does **not** use an LLM, hosted model, paid literature API, or metered research service;
- does **not** send paper content to a model provider;
- uses deterministic, source-bounded extraction and proposal templates written in Python.

The tradeoff is explicit: the generated reports are evidence-organized research-planning aids, not expert narrative reviews. Main findings are extracted from available abstracts, methods are recognized from source text, and every speculative *Xenopus* hypothesis is labeled. A scientist should review the PDF before using it in a grant.

## Sources and evidence boundaries

- Official publisher issue and article URLs are the canonical links.
- Publisher-deposited Crossref metadata is used as the change detector and metadata source.
- Europe PMC is queried for legally available abstracts when Crossref does not contain one.
- Paywalls, robots restrictions, and authentication controls are never bypassed.
- If an official page cannot be retrieved by the runner, the report says so and does not claim full-text or figure review.

## Outputs saved in GitHub

- `pdf/<journal>/<year>/*.pdf` - final landscape infographic PDFs
- `reports/<journal>/<year>/*.json` - structured evidence and proposal records
- `state/journal_issue_monitor_state.json` - exact processed release state

A release is marked processed only after its PDF is created and passes rendered-page QA. If there is no new issue, nothing is regenerated or committed.

## Automation

`.github/workflows/cns-mcdb-update.yml` checks every two hours and can also be run manually. The no-change detector installs only the small `requests` networking dependency and has a three-minute timeout. PDF dependencies are installed only when a new issue is detected; the generation job has a twenty-minute timeout.

The workflow contains no payment credential and no paid API integration. GitHub-hosted Actions usage still counts against the account's included Actions allowance. To make billing enforcement account-wide, keep the GitHub Actions spending limit at **$0** in the account's Billing settings.

## PDF content

For each qualifying primary-research paper, the PDF records:

- title, authors, article type, issue metadata, DOI, and canonical link;
- abstract-supported main discovery, importance, methods, evidence, and limitations;
- a testable early-*Xenopus laevis* or *Xenopus tropicalis* concept;
- importance, knowledge gap, rationale, falsifiable hypothesis, design, controls, replication logic, decision point, expected/refuting/alternative outcomes, pitfalls, backup strategies, and a rapid preliminary-data plan;
- novelty, feasibility, risk, grant fit, and reviewer-facing premise.

Source-supported findings, cross-species inference, speculative hypotheses, and proposed experiments are kept distinct.

## Manual run

Open **Actions > CNS MCDB Update > Run workflow**. Leave `force` disabled for normal operation. Enabling it rebuilds the currently detected issues and uses additional GitHub Actions minutes, but still does not call any model API.

## Local validation

```bash
python -m pip install -r requirements.txt
PYTHONPATH=. python -m pytest -q
```

Tests use synthetic fixtures and do not contact journals or external services.
