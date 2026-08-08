"""Canonical industry taxonomy + normalization for the candidate Industry feature.

Goal: candidates are tagged with the *business/domain* industries they have
worked in (e.g. "FinTech", "Healthcare"), never with their occupation/job
title. This module centralizes the canonical list + alias mapping so every
code path (resume parsing, manual edit, backfill, search/filter) normalizes
to the exact same values — this is what prevents "FinTech" / "Fintech" /
"Financial Technology" from ending up as three different filter buckets.
"""
import re

# Canonical taxonomy shown in the UI picker (dropdown/filter) and used as the
# reference list the LLM is asked to classify against. Recruiters can still
# add a custom value that isn't in this list (normalize_industry then just
# title-cases it consistently so re-typing the same custom value converges).
INDUSTRY_TAXONOMY = [
    'FinTech',
    'Banking / BFSI',
    'Healthcare',
    'HealthTech',
    'EdTech',
    'E-commerce',
    'SaaS',
    'IT / Software',
    'Telecom',
    'FMCG',
    'Manufacturing',
    'Automotive',
    'Oil & Gas',
    'Energy',
    'Real Estate',
    'Consulting',
    'Logistics / Supply Chain',
    'Retail',
    'Media & Entertainment',
    'Government',
    'Insurance',
]

# alias (lowercased, punctuation-stripped) -> canonical value. Covers the
# "duplicate variations" called out in the PRD (FinTech/Fintech/Financial
# Technology, Healthcare/Health Care, BFSI/Banking Financial Services
# Insurance, etc.) plus common synonyms recruiters/LLMs are likely to type.
_ALIASES = {
    'fintech': 'FinTech',
    'financial technology': 'FinTech',
    'financial tech': 'FinTech',
    'bfsi': 'Banking / BFSI',
    'banking': 'Banking / BFSI',
    'bank': 'Banking / BFSI',
    'banking financial services insurance': 'Banking / BFSI',
    'banking and financial services': 'Banking / BFSI',
    'financial services': 'Banking / BFSI',
    'healthcare': 'Healthcare',
    'health care': 'Healthcare',
    'healthtech': 'HealthTech',
    'health technology': 'HealthTech',
    'digital health': 'HealthTech',
    'edtech': 'EdTech',
    'education technology': 'EdTech',
    'education': 'EdTech',
    'ecommerce': 'E-commerce',
    'e commerce': 'E-commerce',
    'e-commerce': 'E-commerce',
    'online retail': 'E-commerce',
    'saas': 'SaaS',
    'software as a service': 'SaaS',
    'it': 'IT / Software',
    'it software': 'IT / Software',
    'information technology': 'IT / Software',
    'software': 'IT / Software',
    'technology': 'IT / Software',
    'tech': 'IT / Software',
    'telecom': 'Telecom',
    'telecommunications': 'Telecom',
    'fmcg': 'FMCG',
    'fast moving consumer goods': 'FMCG',
    'consumer packaged goods': 'FMCG',
    'cpg': 'FMCG',
    'manufacturing': 'Manufacturing',
    'automotive': 'Automotive',
    'auto': 'Automotive',
    'oil gas': 'Oil & Gas',
    'oil and gas': 'Oil & Gas',
    'oil energy': 'Oil & Gas',
    'energy': 'Energy',
    'utilities': 'Energy',
    'renewable energy': 'Energy',
    'real estate': 'Real Estate',
    'realty': 'Real Estate',
    'proptech': 'Real Estate',
    'consulting': 'Consulting',
    'professional services': 'Consulting',
    'logistics': 'Logistics / Supply Chain',
    'supply chain': 'Logistics / Supply Chain',
    'logistics supply chain': 'Logistics / Supply Chain',
    'transportation': 'Logistics / Supply Chain',
    'retail': 'Retail',
    'media': 'Media & Entertainment',
    'entertainment': 'Media & Entertainment',
    'media entertainment': 'Media & Entertainment',
    'gaming': 'Media & Entertainment',
    'government': 'Government',
    'public sector': 'Government',
    'govtech': 'Government',
    'insurance': 'Insurance',
    'insurtech': 'Insurance',
}

# Precompute a lookup of canonical values by their normalized key too, so a
# value that's ALREADY canonical (just different casing/spacing) maps back
# to the exact stored casing instead of being treated as "new".
_CANONICAL_BY_KEY = {}
for _canon in INDUSTRY_TAXONOMY:
    _CANONICAL_BY_KEY[re.sub(r'[^a-z0-9]+', ' ', _canon.lower()).strip()] = _canon


def _norm_key(raw: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', raw.lower()).strip()


def normalize_industry(raw: str) -> str:
    """Map a raw industry string (from the LLM or a recruiter's free-typed
    entry) to a canonical, deduplicated value. Unknown values are title-cased
    so repeated manual entry of the same custom industry still converges to
    one consistent string instead of spawning near-duplicates."""
    raw = (raw or '').strip()
    if not raw:
        return ''
    key = _norm_key(raw)
    if key in _ALIASES:
        return _ALIASES[key]
    if key in _CANONICAL_BY_KEY:
        return _CANONICAL_BY_KEY[key]
    # Unknown/custom industry — keep the recruiter's own wording but
    # normalize whitespace + casing for consistency across records.
    return ' '.join(w.capitalize() if w.islower() else w for w in raw.split())


def normalize_industry_list(raw_list, max_items: int = 8) -> list:
    """Normalize + dedupe a list of raw industry strings, preserving order."""
    out = []
    seen = set()
    for r in raw_list or []:
        norm = normalize_industry(str(r))
        if not norm:
            continue
        k = norm.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(norm)
        if len(out) >= max_items:
            break
    return out


# Prompt snippet shared by resume_parser.py (single-shot classification during
# resume parse) and industry_classifier.py (standalone classification used by
# the backfill migration for candidates with no fresh parse in flight).
INDUSTRY_PROMPT_RULES = f"""Industry classification rules:
- Assign the business/domain industries the candidate has ACTUALLY WORKED IN, based on their employers, job responsibilities, products/services mentioned, and business context described in their work experience.
- Prefer these canonical values when they apply: {', '.join(INDUSTRY_TAXONOMY)}. If none fit well, use a short, specific industry name instead.
- Do NOT infer an industry solely from a job title or occupation (e.g. "Software Engineer" does NOT by itself imply IT / Software or FinTech — only assign an industry if the employer/company's business domain or the work described gives real evidence of it).
- Only include an industry when there is reasonable evidence in the resume. If evidence is thin or ambiguous, leave it out rather than guessing.
- A candidate can have zero, one, or multiple industries (e.g. someone who worked at a bank's technology team and later at a hospital's IT department could be ["Banking / BFSI", "Healthcare"])."""
