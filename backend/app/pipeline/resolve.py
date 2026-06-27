"""Domain-constrained resolution — "validation at each step".

After recognition, each value is validated/corrected against what the DOMAIN
guarantees, before the cross-field rules run. The first and highest-impact
resolver is for Kürzel: handwritten 3-letter initials are the hardest OCR target,
but these records are signed by only a handful of people (the Beteiligte-Personen
roster). We don't need to read the scrawl perfectly — we snap each read to the
nearest registered signer. 'che'/'oh'/'ohc'/'ohp' -> 'ohe'; 'hau'/'has' -> 'han'.
A read that matches no signer within tolerance is flagged for human review.
"""
from __future__ import annotations

import re
from collections import Counter

from app.domain.roles import Role
from app.domain.severity import Category, Severity
from app.pipeline.model import Document, Field, Flag

_KZ = re.compile(r"^[a-zäöüß]{2,5}$")
_DATE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")
_SIGN_ROLES = (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED)


def _field_kuerzel(f: Field) -> tuple[str, str] | None:
    """Return (date, kürzel) if the field is a signature ('date / initials'),
    by ROLE or by VALUE shape — so 'Review/Reviewer' lines resolve too."""
    date, kz = _split_sig(f.value_raw)
    if not kz:
        return None
    if f.role in _SIGN_ROLES or _DATE.match(date or ""):
        return date or "", kz
    return None


def _edits(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein distance, capped."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > cap:
        return cap + 1
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[lb]


def _split_sig(raw: str) -> tuple[str, str | None]:
    parts = (raw or "").split("/")
    date = parts[0].strip()
    kz = parts[1].strip().lower() if len(parts) > 1 else None
    return date, (kz if kz and _KZ.match(kz) else None)


def _roster_kuerzel(doc: Document) -> Counter:
    """Kürzel registered in the personnel table (label contains 'Kürzel')."""
    reg: Counter = Counter()
    for f in doc.all_fields():
        low = (f.label_raw or "").lower()
        if "kürzel" in low or "kuerzel" in low:
            v = (f.value_raw or "").strip().lower()
            _, kz = _split_sig(v) if "/" in v else (None, v if _KZ.match(v) else None)
            if kz:
                reg[kz] += 1
    return reg


def canonical_signers(doc: Document) -> list[str]:
    """The distinct registered signers (deduped spellings).

    Cluster every Kürzel seen (roster + signatures) by edit-distance; each
    cluster is one person. Prefer a roster spelling as the cluster's label,
    else the most frequent 3-letter reading.
    """
    roster = _roster_kuerzel(doc)
    seen: Counter = Counter(roster)
    for f in doc.all_fields():
        sig = _field_kuerzel(f)
        if sig:
            seen[sig[1]] += 1
    if not seen:
        return []

    clusters: list[list[str]] = []
    for kz, _ in seen.most_common():
        for cl in clusters:
            if any(_edits(kz, m, 2) <= 2 for m in cl):
                cl.append(kz)
                break
        else:
            clusters.append([kz])

    labels: list[str] = []
    for cl in clusters:
        roster_members = [m for m in cl if m in roster]
        pool = roster_members or [m for m in cl if len(m) == 3] or cl
        labels.append(max(pool, key=lambda m: (roster[m], seen[m])))
    return labels


def resolve_kuerzel(doc: Document) -> Document:
    signers = canonical_signers(doc)
    if not signers:
        return doc
    for f in doc.all_fields():
        sig = _field_kuerzel(f)
        if not sig:
            continue
        date, kz = sig
        ranked = sorted(((_edits(kz, s, 3), s) for s in signers), key=lambda t: t[0])
        best_d, best = ranked[0]
        second_d = ranked[1][0] if len(ranked) > 1 else 99

        if best_d == 0:
            conf = 0.97
        elif best_d <= 2 and second_d - best_d >= 1:        # close to exactly one signer
            f.value_raw = f"{date} / {best}" if date else best
            f.value = f.value_raw
            conf = 0.95 if best_d == 1 else 0.85
        else:                                               # no clear match -> human
            f.add_flag(Flag(Severity.WARNING, Category.FOUR_EYES, "KUERZEL_UNRESOLVED",
                            f"Signature '{kz}' matches no registered signer ({', '.join(signers)})",
                            expected="a registered signer", actual=kz))
            continue
        # a confident registry match is a real legibility signal -> lift confidence
        f.ocr_confidence = max(f.ocr_confidence or 0.0, conf)
    return doc


def resolve(doc: Document) -> Document:
    """Per-step domain resolution (extensible: dates window, number ranges...)."""
    resolve_kuerzel(doc)
    return doc
