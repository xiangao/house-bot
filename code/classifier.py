"""Classify whether a listing's marketing remarks indicate the house was
built by a builder for themselves (i.e. a builder's personal residence).

The rest of the pipeline (fetch, persistence, HTML badge) is wired to whatever
this function returns. Edit ONLY this file to tune detection.
"""

import re


def is_builder_owned(remarks: str, year_built: int | None = None) -> tuple[bool, str]:
    """Return (matched, evidence_phrase).

    `remarks` is the MLS marketing remarks text (plain, no HTML). May be empty.
    `year_built` is provided in case you want to gate on construction age.

    Return:
        (True,  "builder's own home")    — flagged, with the snippet that matched
        (False, "")                      — not flagged

    Design notes
    ------------
    Whoever built it advertises this loudly because it's a top selling point.
    The signal is in the *phrasing* of the remarks, not the structured fields.
    We catch the same idea expressed through several actors and voices, not
    just the literal word "builder". Typical MLS dialect in Eastern MA /
    Southern NH:

        "Builder's own home..."                         (builder, possessive)
        "Contractor's / developer's personal residence" (other trades)
        "Built by the builder for his family..."         (built-by … for/as self)
        "...built this home for himself / ourselves"     (reflexive)
        "Owner-built craftsman home" / "built by the owner"  (owner-built)
        "We custom built this home as our forever..."    (first-person)
        "Custom built for the owner..."                  (loose; see Tier 3)

    Patterns are organised in three tiers (see the list below):
      - Tier 1 — high-precision reflexive cues across actors
        (builder/contractor/developer/… + own/personal/private, "for
        himself/ourselves", owner-built). Near-zero false positives.
      - Tier 2 — proximity rule, "builder" ONLY. Other actors ("developer
        incentive. Own a…") appear in marketing boilerplate, so they are
        deliberately excluded here; kept within one sentence to avoid
        crossing-period false positives.
      - Tier 3 — LOOSE "(custom) built for the owner". Often means built for a
        *client*, not the builder's own home; remove the line if it produces
        junk. Inspect `builder_match` in data/listings.csv periodically.
      - Gate with `year_built` (e.g. only if >= 2010) to filter the rare case
        where remarks describe a long-ago build history.
    """
    if not remarks:
        return False, ""

    text = remarks.lower()

    # Actor = whoever does the construction and might keep the house for themselves.
    actor = r"(?:builder|contractor|developer|craftsman|carpenter|mason)"

    patterns = [
        # ── Tier 1: high-precision reflexive cues (near-zero false positives) ──
        # "<actor>'s own / personal / private home|residence|house"
        rf"{actor}'?s (?:own|personal|private) (?:home|residence|house)",
        # "built by <…> for/as his|her|their|my|our own|personal|family|…self"
        r"built by .{0,40}\b(?:for|as)\b .{0,20}\b(?:own|personal|family|"
        r"himself|herself|themselves|myself|ourselves)\b",
        # reflexive "built … for himself|herself|themselves|myself|ourselves"
        # (any actor, incl. first-person seller/agent narration)
        r"built\b.{0,30}\bfor (?:himself|herself|themselves|myself|ourselves)\b",
        # owner constructed it themselves
        r"\bowner[\s-]?built\b",
        r"built by (?:the |its )?(?:current |original )?owners?\b",
        # "(personal|private) home|residence of/for the <actor|owner>"
        rf"(?:personal|private) (?:home|residence) (?:of|for) (?:the )?(?:{actor}|owners?)",
        # first-person builder narration: "I/we (custom/hand) built this home|house"
        r"\b(?:i|we) (?:custom[\s-]?|hand[\s-]?)?(?:built|designed and built) this (?:home|house)",

        # ── Tier 2: proximity rule, "builder" ONLY ──
        # Looser actors like "developer"/"contractor" appear in marketing
        # boilerplate ("developer incentive. Own a…", "developer financing"),
        # so the proximity rule is kept to "builder". The gap stays within one
        # sentence (no . ! ?) and ~40 chars. May still flag boilerplate
        # ("quality builder … your family"); inspect matches periodically.
        r"builder\b[^.!?\n]{0,40}?\b(?:own|personal|family|residence)\b",

        # ── Tier 3: LOOSE (false-positive prone). "(custom) built for the owner"
        # often means built for a *client*, not the builder's own home — keep an
        # eye on what this fires on. Remove this line if it produces junk. ──
        r"(?:custom[\s-]?built|custom home built) for (?:the )?(?:current |original )?owners?\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return True, m.group(0)

    return False, ""
