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
    Builders advertise this loudly because it's a top selling point. The signal
    is in the *phrasing* of the remarks, not the structured fields. Typical
    MLS dialect in Eastern MA / Southern NH:

        "Builder's own home..."
        "Custom built by the builder for his family..."
        "Builder's personal residence with the finest finishes..."
        "Built by [Name] Builders as their personal home..."

    Trade-offs to consider as you write patterns:
      - Tight patterns ("builder's own", "builder's personal") = near-zero
        false positives, may miss creative phrasings.
      - Loose patterns ("builder" within N words of "own"/"personal"/"family")
        catch more, risk flagging "from a quality builder" boilerplate.
      - Gate with `year_built` (e.g. only if >= 2010) to filter the rare case
        where remarks describe a long-ago build history.
    """
    if not remarks:
        return False, ""

    text = remarks.lower()

    patterns = [
        r"builder'?s own home",
        r"builder'?s personal (residence|home)",
        r"built by .{0,40} (for|as) (his|her|their) (own|personal|family)",
        # Proximity rule: "builder" within ~6 words of own/personal/family/residence.
        # Inspect matches periodically — may flag boilerplate like
        # "from a quality builder ... your family will love".
        r"builder\b(?:\W+\w+){0,6}\W+(own|personal|family|residence)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return True, m.group(0)

    return False, ""
