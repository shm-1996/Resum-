#!/usr/bin/env python3
"""
fetch_ads_pubs.py

Fetches your NASA ADS library and writes publications.tex in moderncv style.

Usage:
    python fetch_ads_pubs.py

Requirements:
    pip install requests
"""

import os
import sys
import datetime
import requests

# ── Configuration ────────────────────────────────────────────────────────────

ADS_TOKEN         = "TW9jSgvsDz6QqOCG1t1CG9T8GSAFGFaEPJXbeVy9"
LIBRARY_ID        = "2ISqHbaiQ9-l2n4w4stzSw"
YOUR_NAME         = "Menon"          # last name only — matched against raw ADS strings
YOUR_NAME_DISPLAY = "Menon, S.H."    # how your name is typeset in the output
MAX_AUTHORS       = 6                # truncate long author lists with et al.

# Journals where you want to suppress the volume/page (e.g. submitted papers)
SUBMITTED_KEYWORDS = {"submitted", "in prep", "in preparation"}

# ── ADS API helpers ───────────────────────────────────────────────────────────

BASE = "https://api.adsabs.harvard.edu/v1"
HEADERS = {"Authorization": f"Bearer {ADS_TOKEN}"}

FIELDS = ",".join([
    "bibcode", "title", "author", "year", "pub", "volume", "page",
    "citation_count", "identifier", "doctype", "pubdate", "arxiv_class"
])


def get_library_bibcodes(library_id: str) -> list[str]:
    """Return all bibcodes in the library (handles pagination)."""
    bibcodes = []
    rows = 100
    start = 0
    while True:
        r = requests.get(
            f"{BASE}/biblib/libraries/{library_id}",
            headers=HEADERS,
            params={"rows": rows, "start": start},
        )
        r.raise_for_status()
        data = r.json()
        docs = data.get("documents", [])
        bibcodes.extend(docs)
        if len(docs) < rows:
            break
        start += rows
    return bibcodes


def get_paper_details(bibcodes: list[str]) -> list[dict]:
    """Fetch full metadata for a list of bibcodes."""
    joined = " OR ".join(f"bibcode:{b}" for b in bibcodes)
    r = requests.get(
        f"{BASE}/search/query",
        headers=HEADERS,
        params={
            "q": joined,
            "fl": FIELDS,
            "rows": 500,
            "sort": "pubdate desc",
        },
    )
    r.raise_for_status()
    return r.json()["response"]["docs"]


# ── Name helpers ──────────────────────────────────────────────────────────────

def is_you(author: str) -> bool:
    """Match against a raw ADS author string e.g. 'Menon, Shyam H.'"""
    return YOUR_NAME in author


def fmt_author(raw: str) -> str:
    """Abbreviate 'Last, First Middle' → 'Last, F.' and bold if it's you."""
    parts = raw.split(", ")
    if len(parts) == 2:
        name = f"{parts[0]}, {parts[1][0]}."
    else:
        name = raw
    if is_you(raw):
        return r"\textbf{" + name + r"}"
    return name


def format_authors(authors: list[str]) -> str:
    formatted = [fmt_author(a) for a in authors]
    if len(formatted) > MAX_AUTHORS:
        truncated = formatted[:MAX_AUTHORS]
        # If you fall outside the truncated window, flag it explicitly
        if not any(is_you(a) for a in authors[:MAX_AUTHORS]):
            truncated.append(r"\textbf{incl. " + YOUR_NAME_DISPLAY + r"}")
        truncated.append(r"et al.")
        return ", ".join(truncated)
    return ", ".join(formatted)


# ── Formatting helpers ────────────────────────────────────────────────────────

def latex_escape(s: str) -> str:
    return s.replace("&", r"\&").replace("_", r"\_").replace("#", r"\#")


def arxiv_url(paper: dict) -> str | None:
    for ident in paper.get("identifier", []):
        if ident.startswith("arXiv:"):
            arxiv_id = ident.replace("arXiv:", "")
            return f"https://arxiv.org/abs/{arxiv_id}"
    return None


def ads_url(bibcode: str) -> str:
    return f"https://ui.adsabs.harvard.edu/abs/{bibcode}/abstract"


def format_journal_ref(paper: dict) -> str:
    pub   = paper.get("pub", "")
    year  = paper.get("year", "")
    vol   = paper.get("volume", "")
    pages = paper.get("page", [""])[0] if paper.get("page") else ""

    if any(kw in pub.lower() for kw in SUBMITTED_KEYWORDS):
        return f"{pub}, {year}"

    abbrevs = {
        "The Astrophysical Journal":                         "ApJ",
        "The Astrophysical Journal Letters":                 "ApJL",
        "The Astrophysical Journal Supplement Series":       "ApJS",
        "Monthly Notices of the Royal Astronomical Society": "MNRAS",
        "Monthly Notices of the Royal Astronomical Society Letters": "MNRAS Letters",
        "Astronomy & Astrophysics":                          "A\\&A",
        "The Astronomical Journal":                          "AJ",
        "Nature":                                            "Nature",
        "Nature Astronomy":                                  "Nat. Astron.",
        "Science":                                           "Science",
        "Journal of Computational Physics":                  "J. Comput. Phys.",
    }
    pub_short = abbrevs.get(pub, pub)
    parts = [pub_short, year]
    if vol:
        parts.append(vol)
    if pages:
        parts.append(pages)
    return ", ".join(parts)


def citation_tag(n: int | None) -> str:
    if n and n > 0:
        return r" {\scriptsize [" + str(n) + r" Citations]}"
    return ""


def paper_to_latex(paper: dict) -> str:
    title   = latex_escape(paper.get("title", ["Untitled"])[0])
    authors = format_authors(paper.get("author", []))
    jref    = format_journal_ref(paper)
    cites   = citation_tag(paper.get("citation_count"))
    url     = arxiv_url(paper) or ads_url(paper["bibcode"])

    return "\n".join([
        r"    \item",
        f"    \\href{{{url}}}{{{{{title}}}{cites}}} \\\\",
        f"    {authors} \\textcolor{{RedViolet}}{{{{{jref}}}}}",
    ])


# ── Author-position helpers ───────────────────────────────────────────────────

def author_position(paper: dict) -> int:
    for i, a in enumerate(paper.get("author", []), 1):
        if is_you(a):
            return i
    return 0


# ── Writers ───────────────────────────────────────────────────────────────────

def make_header(filename: str, n_total: int, n_first: int, n_second: int, n_collab: int) -> str:
    today   = datetime.date.today().isoformat()
    lib_url = f"https://ui.adsabs.harvard.edu/public-libraries/{LIBRARY_ID}"
    return (
        f"% {filename}\n"
        f"% Auto-generated by fetch_ads_pubs.py — do not edit by hand.\n"
        f"% Last synced: {today}\n\n"
        r"\textbf{\textit{" + str(n_total) +
        r" refereed publications: " + str(n_first) +
        r" first-author, " + str(n_second) +
        r" second-author, " + str(n_collab) +
        r" collaborator" +
        "\n(\\href{" + lib_url + r"}{ADS Listing})}}"
    )


def write_publist(filename: str, paper_list: list[dict], header_counts: tuple) -> None:
    n_total, n_first, n_second, n_collab = header_counts
    lines = [make_header(filename, n_total, n_first, n_second, n_collab), ""]
    lines.append(r"\begin{enumerate}")
    lines.append("")
    for paper in paper_list:
        lines.append(paper_to_latex(paper))
        lines.append("")
    lines.append(r"\end{enumerate}")
    with open(filename, "w") as f:
        f.write("\n".join(lines))
    print(f"Written to {filename}  ({len(paper_list)} papers).")


def write_full_doc(filename: str, paper_list: list[dict],
                   n_first: int, n_second: int, n_collab: int) -> None:
    today   = datetime.date.today().isoformat()
    lib_url = f"https://ui.adsabs.harvard.edu/public-libraries/{LIBRARY_ID}"
    n_total = len(paper_list)

    preamble = rf"""% {filename}
% Auto-generated by fetch_ads_pubs.py — do not edit by hand.
% Last synced: {today}
% Compile with: pdflatex {filename}

\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[top=1in,bottom=1in,left=1in,right=1in]{{geometry}}
\usepackage{{hyperref}}
\usepackage[dvipsnames]{{xcolor}}
\usepackage{{enumitem}}
\hypersetup{{colorlinks=true, urlcolor=blue, linkcolor=blue}}
\urlstyle{{same}}

\title{{Publication List}}
\author{{Shyam Harimohan Menon}}
\date{{Last synced: {today}}}

\begin{{document}}
\maketitle

\noindent\textbf{{\textit{{{n_total} refereed publications: {n_first} first-author, {n_second} second-author, {n_collab} collaborator
(\href{{{lib_url}}}{{ADS Listing}})}}}}

\begin{{enumerate}}[leftmargin=*, label={{[\arabic*]}}]

"""
    paper_lines = "\n\n".join(paper_to_latex(p) for p in paper_list)
    postamble = "\n\n\\end{enumerate}\n\\end{document}\n"

    with open(filename, "w") as f:
        f.write(preamble + paper_lines + postamble)
    print(f"Written to {filename}  ({n_total} papers).")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not ADS_TOKEN:
        sys.exit(
            "Error: ADS_API_TOKEN environment variable not set.\n"
            "Get a token at https://ui.adsabs.harvard.edu/user/settings/token"
        )

    print(f"Fetching library {LIBRARY_ID} …")
    bibcodes = get_library_bibcodes(LIBRARY_ID)
    print(f"  Found {len(bibcodes)} bibcodes.")

    print("Fetching paper details …")
    papers = get_paper_details(bibcodes)
    print(f"  Retrieved {len(papers)} papers.")

    # Sort all papers latest-first
    papers.sort(key=lambda p: p.get("pubdate", ""), reverse=True)

    # Counts over the full list
    first  = sum(1 for p in papers if author_position(p) == 1)
    second = sum(1 for p in papers if author_position(p) == 2)
    collab = sum(1 for p in papers if author_position(p) > 2)

    # Lead-author subset for the CV: first-author papers first, then 2nd/3rd
    # All groups maintain latest-first order (papers is already sorted that way)
    first_author  = [p for p in papers if author_position(p) == 1]
    other_lead    = [p for p in papers if 2 <= author_position(p) <= 4]
    lead_papers   = first_author + other_lead

    # publications.tex — lead authors only, but header reflects full counts
    write_publist(
        "publications.tex",
        lead_papers,
        (len(papers), first, second, collab),
    )

    # publications_full.tex — all papers, standalone compilable document
    write_full_doc("publications_full.tex", papers, first, second, collab)


if __name__ == "__main__":
    main()