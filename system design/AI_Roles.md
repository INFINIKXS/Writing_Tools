# AI Roles in Citation Verification — System Design

## Overview

The Writing Tools application uses **Gemini AI** (`gemini-3-flash-preview`) in two distinct endpoints. Everything else — file parsing, string matching, verbatim extraction, progress streaming — is handled by deterministic Python code.

---

## 1. Citation Verifier (`POST /api/verify`)

**File:** [`main.py`](../backend/main.py) — lines 305–335

The AI receives the **entire document text** (up to 1M characters) and performs four tasks in a single prompt:

### What the AI Does

| Task | Description | Why AI Is Needed |
|---|---|---|
| **Citation Extraction** | Scans the body text and lists every unique in-text citation (`(Smith, 2020)`, `[1]`, `Author (Year)`, etc.) | Citations come in many inconsistent formats — regex alone can't reliably catch all variants |
| **Reference Extraction** | Finds the reference list section (under "References", "Bibliography", etc.) and extracts each individual reference | AI understands document structure — it knows where the body ends and the reference list begins |
| **Cross-Matching** | Maps each citation to its corresponding reference entry | The AI understands that `(Smith et al., 2020)` matches `Smith, J., Brown, A. and Lee, C. (2020)…` — something basic string matching would miss |
| **Irregularity Detection** | Flags date mismatches, spelling errors (`Smith` vs `Smyth`), formatting issues, and duplicates | This requires semantic understanding — recognizing that names/dates are *close* but not identical |

### AI Output Format

The AI returns structured JSON:

```json
{
  "in_text_citations": ["(Smith, 2020)", "(Brown et al., 2019)", ...],
  "references": ["Smith, J. (2020) Title...", "Brown, A. (2019) Title...", ...],
  "missing_references_for_citations": ["(Jones, 2021)"],
  "unused_references": ["Lee, C. (2018) Title..."],
  "irregularities": [
    {
      "type": "date_mismatch",
      "citation": "Author (2020)",
      "ref": "Author (2019)",
      "details": "Year differs"
    }
  ],
  "summary": "Brief overview of issues found."
}
```

### What Happens After the AI (Python, No AI)

| Function | Purpose |
|---|---|
| `verify_matches_with_string_search()` | Deterministic sanity check — extracts first author surnames from citations and references, does case-insensitive exact matching. Generates the `confirmed_matches` list. |
| `extract_verbatim_references()` | Extracts the **exact verbatim text** from the source document for each AI-identified reference (see safeguards below). |

### Safeguards in `extract_verbatim_references()` (Preventing DOI Bleeding & Mixups)

| Safeguard | How It Works |
|---|---|
| **1. Reference Section Isolation** | Locates the "References" / "Bibliography" / "Works Cited" heading via regex and only searches within that section — body text is excluded entirely. |
| **2. Atomic Splitting (Anti-DOI-Bleed)** | Instead of blindly joining adjacent lines, the algorithm parses the reference section into **complete, atomic entries**. A new reference is detected when a line starts with an author-name pattern (`Surname,`). Lines starting with DOIs, URLs, `Available at`, `Accessed`, `pp.`, `Vol.`, `Issue`, or `Retrieved` are treated as **continuation lines** — they always belong to the previous reference, never the next one. This prevents a DOI from one reference bleeding into an adjacent entry. |
| **3. Author + Year Compound Key** | Matching uses both the first author surname AND the publication year. A candidate reference must contain **both** the same author name and the same year to be considered. This prevents `Smith (2019)` from matching `Smith (2021)`. |
| **4. Conflict Detection** | If two different AI-identified references resolve to the **same** verbatim text, a warning is flagged in the response (`"conflict"` field) and displayed in the UI with an amber border. |

---

## 2. Reference Formatter (`POST /api/format`)

**File:** [`main.py`](../backend/main.py) — lines 391–432

For each raw reference the user inputs, the AI:

1. **Classifies** the reference type (Book, Journal Article, Web page, etc.)
2. **Reformats** it to exact Harvard style using the `HARVARD_GUIDE` — a comprehensive 8,000+ word guide injected into the prompt from [`harvard_guide.py`](../backend/harvard_guide.py)
3. Returns JSON with `original`, `type`, and `formatted` fields

This uses Gemini as a **subject-matter expert** on Harvard referencing conventions.

---

## Division of Labor: AI vs. Python

```
AI (Gemini)                          Python (No AI)
─────────────────────────────────    ─────────────────────────────────
• Understanding document structure   • File parsing (PDF/DOCX/DOC)
• Identifying citation formats       • Magic byte format detection
• Semantic cross-matching            • First-author string matching
• Detecting name/date irregularities • Verbatim source text extraction
• Harvard format classification      • SSE progress streaming
• Reference reformatting             • JSON response assembly
```

---

## Processing Pipeline

```
Upload File
    │
    ▼
┌──────────────────────┐
│  File Parsing        │  ← Python: PyPDF2 / python-docx / olefile
│  (magic byte detect) │
└──────────┬───────────┘
           │ raw text
           ▼
┌──────────────────────┐
│  Gemini AI Analysis  │  ← AI: citation extraction, reference extraction,
│                      │       cross-matching, irregularity detection
└──────────┬───────────┘
           │ structured JSON
           ▼
┌──────────────────────┐
│  String Verification │  ← Python: first-author surname matching
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Verbatim Extraction │  ← Python: SequenceMatcher fuzzy match
│                      │       against original document text
└──────────┬───────────┘
           │
           ▼
        Results
```
