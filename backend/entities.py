"""
Layer 2 — NLP: Entity Extractor
Notebook section 9: spaCy en_core_web_sm + regex patterns.
Extracts: products/modules (NER), error codes, versions, platform/OS, URLs/paths.
"""

import re
from typing import Optional

_nlp = None


def _get_nlp():
    """Lazy-load spaCy model. Falls back gracefully if model not installed."""
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        _nlp = False   # sentinel: tried but failed
    return _nlp


def extract_entities(text: str) -> dict:
    """
    Extract structured entities from ticket text.
    Returns dict with: products_or_modules, error_codes, versions,
                       platform_os, urls_or_paths.
    """
    text = str(text)
    out = {
        "products_or_modules": [],
        "error_codes":         [],
        "versions":            [],
        "platform_os":         [],
        "urls_or_paths":       [],
    }

    # spaCy NER for products / org names
    nlp = _get_nlp()
    if nlp:
        doc = nlp(text[:100_000])
        for ent in doc.ents:
            if ent.label_ in ("PRODUCT", "ORG", "WORK_OF_ART"):
                out["products_or_modules"].append(ent.text)

    # Regex patterns (notebook section 9 — exact match)
    out["error_codes"] = re.findall(
        r"\b(?:ERR|ERROR|HTTP|BUG|EXC|CODE)?[-_ ]?\d{3,6}\b", text, flags=re.I
    )
    out["versions"] = re.findall(
        r"\bv?\d+\.\d+(?:\.\d+)?(?:[-_][A-Za-z0-9]+)?\b", text
    )
    out["platform_os"] = re.findall(
        r"\bWindows|Linux|Ubuntu|Debian|macOS|Mac\s*OS|Android|iOS|"
        r"Chrome|Firefox|Safari|Edge|Opera\b",
        text, flags=re.I
    )
    out["urls_or_paths"] = re.findall(
        r"(?:/[\w\-.]+)+|https?://\S+", text
    )

    # Deduplicate + truncate (notebook: [:10])
    for k in out:
        out[k] = sorted(list(set(x.strip() for x in out[k] if str(x).strip())))[:10]

    return out
