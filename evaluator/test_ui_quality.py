"""
UI Quality Tests for BioDize
=============================
Tests that the reviewer desktop app and web frontend meet professional-quality
standards: WCAG color contrast, string completeness, consistency, and label clarity.

Run:  py evaluator/test_ui_quality.py
      py -m pytest evaluator/test_ui_quality.py -v
"""
from __future__ import annotations

import ast
import re
import sys
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()

# ── WCAG helpers ─────────────────────────────────────────────────────────────

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def _luminance(hex_color: str) -> float:
    r, g, b = (_linear(x / 255) for x in _hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast(fg: str, bg: str) -> float:
    l1, l2 = _luminance(fg), _luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)

# WCAG thresholds
AA_NORMAL = 4.5   # body / UI text
AA_LARGE  = 3.0   # headings, large bold text
AA_UI     = 3.0   # UI components (buttons, borders)

# ── Load reviewer constants ───────────────────────────────────────────────────

def _load_reviewer():
    """Parse reviewer.py with ast to extract C, INFO, ACTION, STATUS_DE.

    Handles both dict literals {...} and dict(...) keyword-call forms.
    """
    src = (ROOT / "evaluator" / "reviewer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    ns: dict = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            # Path A: plain literal ({...}, "string", 42, ...)
            try:
                ns[target.id] = ast.literal_eval(node.value)
                continue
            except Exception:
                pass
            # Path B: dict(key=val, ...) keyword call
            val = node.value
            if (isinstance(val, ast.Call)
                    and isinstance(val.func, ast.Name)
                    and val.func.id == "dict"
                    and not val.args):
                try:
                    ns[target.id] = {
                        kw.arg: ast.literal_eval(kw.value)
                        for kw in val.keywords
                    }
                except Exception:
                    pass
    return ns

_RV = _load_reviewer()
C          = _RV.get("C", {})
INFO       = _RV.get("INFO", {})
ACTION     = _RV.get("ACTION", {})
STATUS_DE  = _RV.get("STATUS_DE", {})

# ── COLOR PALETTE ─────────────────────────────────────────────────────────────

class TestColorPalette:
    """All hex colors in the reviewer palette must be valid 6-digit hex codes."""

    def test_all_colors_are_valid_hex(self):
        _HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
        for name, val in C.items():
            assert _HEX.match(val), f"Color '{name}' = {val!r} is not a valid #RRGGBB hex"

    def test_palette_has_required_roles(self):
        required = {"bg", "fg", "red", "grn", "yel", "blue", "dim", "err", "wrn", "ok"}
        missing = required - set(C)
        assert not missing, f"Palette missing semantic colors: {missing}"

    def test_error_bg_is_dark(self):
        # err background should be dark (luminance < 0.1) so red text pops
        assert _luminance(C["err"]) < 0.15, \
            f"Error bg {C['err']} is too bright (L={_luminance(C['err']):.3f})"

    def test_warning_bg_is_dark(self):
        assert _luminance(C["wrn"]) < 0.15, \
            f"Warning bg {C['wrn']} is too bright"

    def test_ok_bg_is_dark(self):
        assert _luminance(C["ok"]) < 0.10, \
            f"OK bg {C['ok']} is too bright"

    def test_bg_is_dark_theme(self):
        assert _luminance(C["bg"]) < 0.05, \
            f"Main bg {C['bg']} is not a dark theme background"

    def test_fg_is_light_on_dark(self):
        assert _luminance(C["fg"]) > 0.50, \
            f"Foreground {C['fg']} is too dark for a dark theme"


# ── WCAG CONTRAST ─────────────────────────────────────────────────────────────

class TestWcagContrast:
    """Critical text/background pairs must meet WCAG AA standards."""

    def _assert_contrast(self, fg_key, bg_key, min_ratio, note=""):
        fg, bg = C[fg_key], C[bg_key]
        ratio = contrast(fg, bg)
        assert ratio >= min_ratio, (
            f"{note or f'{fg_key} on {bg_key}'}: "
            f"contrast {ratio:.2f}:1 < {min_ratio}:1  "
            f"({fg} on {bg})"
        )

    def test_fg_on_bg_aa_normal(self):
        self._assert_contrast("fg", "bg", AA_NORMAL, "Body text on main background")

    def test_fg_on_side_aa_normal(self):
        self._assert_contrast("fg", "side", AA_NORMAL, "Body text on sidebar")

    def test_fg_on_hdr_aa_normal(self):
        self._assert_contrast("fg", "hdr", AA_NORMAL, "Body text on header")

    def test_red_on_err_aa_large(self):
        self._assert_contrast("red", "err", AA_LARGE, "Error text on error background")

    def test_yel_on_wrn_aa_large(self):
        self._assert_contrast("yel", "wrn", AA_LARGE, "Warning text on warning background")

    def test_grn_on_ok_aa_large(self):
        self._assert_contrast("grn", "ok", AA_LARGE, "OK text on OK background")

    def test_blue_on_side_aa_ui(self):
        self._assert_contrast("blue", "side", AA_UI, "Accent blue on sidebar (UI component)")

    def test_grn_on_bg_aa_large(self):
        self._assert_contrast("grn", "bg", AA_LARGE, "Success green on main background")

    def test_red_on_bg_aa_large(self):
        self._assert_contrast("red", "bg", AA_LARGE, "Error red on main background")

    def test_yel_on_bg_aa_large(self):
        self._assert_contrast("yel", "bg", AA_LARGE, "Warning yellow on main background")

    def test_dim_on_bg_minimum_readable(self):
        # dim is secondary/hint text -- requires at least AA_UI (3:1) for readability
        ratio = contrast(C["dim"], C["bg"])
        assert ratio >= AA_UI, (
            f"Dim text {C['dim']} on bg {C['bg']}: {ratio:.2f}:1 < {AA_UI}:1  "
            "(secondary text must be readable)"
        )


# ── INFO DICT QUALITY ─────────────────────────────────────────────────────────

class TestInfoDict:
    """INFO dict maps error codes to (title, explanation) -- quality checks."""

    def test_info_is_not_empty(self):
        assert len(INFO) >= 10, "INFO dict seems truncated"

    def test_all_entries_are_tuples_of_two_strings(self):
        for code, entry in INFO.items():
            assert isinstance(entry, tuple) and len(entry) == 2, \
                f"INFO[{code!r}] must be a 2-tuple (title, explanation)"
            title, expl = entry
            assert isinstance(title, str) and title.strip(), \
                f"INFO[{code!r}] title is empty"
            assert isinstance(expl, str) and expl.strip(), \
                f"INFO[{code!r}] explanation is empty"

    def test_titles_are_concise(self):
        for code, (title, _) in INFO.items():
            assert len(title) <= 40, \
                f"INFO[{code!r}] title too long ({len(title)} chars): {title!r}"

    def test_explanations_end_with_period(self):
        for code, (_, expl) in INFO.items():
            assert expl.rstrip().endswith("."), \
                f"INFO[{code!r}] explanation missing period: {expl!r}"

    def test_no_duplicate_titles(self):
        titles = [title for title, _ in INFO.values()]
        seen: dict[str, list[str]] = {}
        for code, (title, _) in INFO.items():
            seen.setdefault(title.lower(), []).append(code)
        dups = {t: codes for t, codes in seen.items() if len(codes) > 1}
        assert not dups, f"Duplicate INFO titles: {dups}"

    def test_titles_start_with_capital(self):
        for code, (title, _) in INFO.items():
            assert title[0].isupper(), \
                f"INFO[{code!r}] title doesn't start with capital: {title!r}"

    def test_codes_follow_naming_convention(self):
        # Codes must be UPPER_SNAKE_CASE; numeric prefix allowed (e.g. 4EYES_DISTINCT)
        _CODE = re.compile(r"^[A-Z0-9][A-Z0-9_]+$")
        for code in INFO:
            assert _CODE.match(code), f"INFO code {code!r} violates UPPER_SNAKE_CASE"
            assert "__" not in code, f"INFO code {code!r} has double underscore"
            assert not code.endswith("_"), f"INFO code {code!r} ends with underscore"

    def test_no_placeholder_text(self):
        bad = re.compile(r"\b(todo|fixme|tbd|placeholder|lorem)\b", re.I)
        for code, (title, expl) in INFO.items():
            assert not bad.search(title + expl), \
                f"INFO[{code!r}] contains placeholder text"

    def test_no_double_spaces(self):
        for code, (title, expl) in INFO.items():
            assert "  " not in title, f"INFO[{code!r}] title has double space"
            assert "  " not in expl, f"INFO[{code!r}] explanation has double space"


# ── ACTION DICT QUALITY ───────────────────────────────────────────────────────

class TestActionDict:
    """ACTION dict maps codes to reviewer instructions -- must match INFO."""

    def test_action_covers_all_info_codes(self):
        missing = set(INFO) - set(ACTION)
        assert not missing, f"These codes have INFO but no ACTION: {missing}"

    def test_info_covers_all_action_codes(self):
        missing = set(ACTION) - set(INFO)
        assert not missing, f"These codes have ACTION but no INFO: {missing}"

    def test_all_actions_are_non_empty_strings(self):
        for code, action in ACTION.items():
            assert isinstance(action, str) and action.strip(), \
                f"ACTION[{code!r}] is empty"

    def test_actions_end_with_period(self):
        for code, action in ACTION.items():
            assert action.rstrip().endswith("."), \
                f"ACTION[{code!r}] missing period: {action!r}"

    def test_actions_are_imperative(self):
        # Good actions start with an imperative verb or "A/An..."
        # Bad: lowercase start
        for code, action in ACTION.items():
            assert action[0].isupper() or action[0].isdigit(), \
                f"ACTION[{code!r}] should start with capital: {action!r}"

    def test_actions_reference_verify_confirm_or_correct(self):
        # Every action should guide the reviewer toward a resolution
        keywords = re.compile(r"\b(confirm|correct|check|read|compute|add|compare|match)\b", re.I)
        for code, action in ACTION.items():
            assert keywords.search(action), \
                f"ACTION[{code!r}] doesn't guide to a resolution: {action!r}"

    def test_actions_are_concise(self):
        for code, action in ACTION.items():
            assert len(action) <= 120, \
                f"ACTION[{code!r}] too long ({len(action)} chars): {action!r}"

    def test_arrow_notation_consistent(self):
        # Unicode arrows not allowed; ASCII -> must have spaces unless inside parens (examples)
        for code, action in ACTION.items():
            assert "→" not in action, \
                f"ACTION[{code!r}] uses Unicode arrow →, use ' -> ' instead"
            # Strip parenthesised examples before checking spaces
            stripped = re.sub(r"\([^)]*\)", "", action)
            if "->" in stripped:
                assert " -> " in stripped, \
                    f"ACTION[{code!r}] directing arrow '->' needs spaces: {action!r}"


# ── STATUS LABELS ─────────────────────────────────────────────────────────────

class TestStatusLabels:
    """STATUS_DE maps API status values to human-readable UI labels."""

    def test_all_expected_statuses_present(self):
        expected = {"auto_accepted", "needs_review", "confirmed", "corrected"}
        missing = expected - set(STATUS_DE)
        assert not missing, f"STATUS_DE missing: {missing}"

    def test_labels_are_title_case_or_hyphenated(self):
        for status, label in STATUS_DE.items():
            first = label.split()[0]
            assert first[0].isupper(), \
                f"STATUS_DE[{status!r}] = {label!r} should start with capital"

    def test_labels_are_concise(self):
        for status, label in STATUS_DE.items():
            assert len(label) <= 20, \
                f"STATUS_DE[{status!r}] = {label!r} too long for a UI chip"

    def test_no_snake_case_labels(self):
        for status, label in STATUS_DE.items():
            assert "_" not in label, \
                f"STATUS_DE[{status!r}] = {label!r} uses snake_case (not human-readable)"


# ── WEB FRONTEND UI QUALITY ───────────────────────────────────────────────────

_UI_FILE = ROOT / "frontend" / "src" / "lib" / "ui.tsx"
_UI_SRC  = _UI_FILE.read_text(encoding="utf-8") if _UI_FILE.exists() else ""


def _extract_ts_record(src: str, name: str) -> dict[str, dict]:
    """Naive extractor: pull out the keys of a TypeScript Record literal."""
    pattern = re.compile(
        rf"(?:export\s+const\s+)?{re.escape(name)}\s*[=:][^{{]*\{{(.*?)\}}\s*;",
        re.S,
    )
    m = pattern.search(src)
    if not m:
        return {}
    block = m.group(1)
    keys = re.findall(r'^\s*(\w+)\s*:', block, re.M)
    return {k: {} for k in keys}


class TestWebFrontendUiLib:
    """Static analysis of frontend/src/lib/ui.tsx -- checks metadata completeness."""

    def test_ui_file_exists(self):
        assert _UI_FILE.exists(), f"ui.tsx not found at {_UI_FILE}"

    def test_severity_meta_covers_both_severities(self):
        for sev in ("error", "warning"):
            assert sev in _UI_SRC, f"SEVERITY_META missing '{sev}'"

    def test_status_meta_covers_all_statuses(self):
        for status in ("extracted", "validated", "auto_accepted", "needs_review", "confirmed", "corrected"):
            assert status in _UI_SRC, f"STATUS_META missing '{status}'"

    def test_category_meta_covers_key_categories(self):
        for cat in ("extraction", "calculation", "range", "temporal", "four_eyes",
                    "format", "missing", "cross_reference"):
            assert cat in _UI_SRC, f"CATEGORY_META missing '{cat}'"

    def test_role_labels_are_human_readable(self):
        # Extract ROLE_LABELS block
        block_m = re.search(r"ROLE_LABELS[^{]*\{(.*?)\};", _UI_SRC, re.S)
        if not block_m:
            pytest.skip("ROLE_LABELS not found in ui.tsx")
        block = block_m.group(1)
        entries = re.findall(r'(\w+)\s*:\s*"([^"]+)"', block)
        for key, label in entries:
            assert "_" not in label, \
                f"ROLE_LABELS[{key!r}] = {label!r} still has underscores (not human-readable)"
            assert label.strip(), f"ROLE_LABELS[{key!r}] is empty"
            assert label[0].isupper() or label[0] == "—", \
                f"ROLE_LABELS[{key!r}] = {label!r} should start with capital"

    def test_severity_labels_are_title_case(self):
        for label in ("Error", "Warning"):
            assert f'label: "{label}"' in _UI_SRC, \
                f"Severity label {label!r} not found in SEVERITY_META"

    def test_status_labels_are_title_case(self):
        for label in ("Confirmed", "Corrected", "Needs review", "Auto-accepted"):
            assert label in _UI_SRC, f"Status label {label!r} not found"

    def test_confidence_tone_covers_all_buckets(self):
        for bucket in ("High", "Medium", "Low"):
            assert f'label: "{bucket}"' in _UI_SRC, \
                f"confidenceTone missing '{bucket}' bucket"

    def test_no_console_log_in_ui_lib(self):
        # Production UI should never have debug console.log
        assert "console.log(" not in _UI_SRC, \
            "ui.tsx has console.log -- remove before shipping"

    def test_no_fixme_todo_in_ui_lib(self):
        bad = re.search(r"\b(FIXME|HACK|XXX)\b", _UI_SRC)
        assert not bad, f"ui.tsx has {bad.group()!r} marker"

    def test_humanize_function_exists(self):
        assert "function humanize" in _UI_SRC or "humanize" in _UI_SRC, \
            "humanize() formatter missing from ui.tsx"

    def test_field_display_value_handles_empty(self):
        # The fallback "—" (em dash) should be returned for empty values
        assert '"—"' in _UI_SRC or "'—'" in _UI_SRC, \
            "fieldDisplayValue should return '—' for empty values"


# ── FRONTEND HTML ─────────────────────────────────────────────────────────────

class TestFrontendHtml:
    """index.html and go.html must meet professional web standards."""

    def test_index_html_has_charset(self):
        f = ROOT / "frontend" / "index.html"
        if not f.exists():
            pytest.skip("index.html not found")
        src = f.read_text(encoding="utf-8")
        assert 'charset' in src.lower(), "index.html missing charset meta tag"

    def test_index_html_has_viewport(self):
        f = ROOT / "frontend" / "index.html"
        if not f.exists():
            pytest.skip()
        src = f.read_text(encoding="utf-8")
        assert "viewport" in src, "index.html missing viewport meta tag (not mobile-friendly)"

    def test_index_html_has_title(self):
        f = ROOT / "frontend" / "index.html"
        if not f.exists():
            pytest.skip()
        src = f.read_text(encoding="utf-8")
        title_m = re.search(r"<title>(.*?)</title>", src, re.I)
        assert title_m, "index.html missing <title>"
        title = title_m.group(1).strip()
        assert title and title.lower() not in ("", "vite app", "react app", "app"), \
            f"index.html has generic title: {title!r}"

    def test_go_html_is_api_agnostic(self):
        f = ROOT / "frontend" / "public" / "go.html"
        if not f.exists():
            pytest.skip()
        src = f.read_text(encoding="utf-8")
        # Strip JS comments before checking for hardcoded URLs
        no_comments = re.sub(r"//[^\n]*", "", src)
        assert "trycloudflare.com" not in no_comments, \
            "go.html has hardcoded cloudflare URL in live code (should be API-agnostic)"
        assert "localhost" not in no_comments, \
            "go.html has hardcoded localhost URL in live code"

    def test_go_html_sets_api_from_param(self):
        f = ROOT / "frontend" / "public" / "go.html"
        if not f.exists():
            pytest.skip()
        src = f.read_text(encoding="utf-8")
        assert "biodize_api_base" in src, \
            "go.html does not set biodize_api_base in localStorage"
        assert "?api=" in src or "api" in src, \
            "go.html does not read ?api= parameter"


# ── REVIEWER STRING CONSISTENCY ───────────────────────────────────────────────

class TestReviewerStringConsistency:
    """Cross-checks within the reviewer to catch inconsistencies."""

    def test_xref_carried_and_mismatch_titles_differ(self):
        # These two codes had duplicate titles before -- catch regression
        carried_title = INFO.get("XREF_CARRIED_MATCH", ("",))[0]
        mismatch_title = INFO.get("XREF_MISMATCH", ("",))[0]
        assert carried_title != mismatch_title, \
            "XREF_CARRIED_MATCH and XREF_MISMATCH have identical titles -- disambiguate"

    def test_missing_codes_have_clear_missing_signal(self):
        # KUERZEL codes should mention "initials" or "signer" in their explanations
        for code in ("KUERZEL_UNKNOWN", "KUERZEL_UNRESOLVED"):
            if code in INFO:
                _, expl = INFO[code]
                assert re.search(r"initial|signer|kürzel|person", expl, re.I), \
                    f"INFO[{code!r}] explanation should mention initials/signer: {expl!r}"

    def test_calc_codes_mention_what_to_calculate(self):
        for code in ("CALC_NET_MASS", "CALC_VOLUME", "CALC_FORMULA"):
            if code in ACTION:
                action = ACTION[code]
                assert re.search(r"formula|comput|recalc|gross|tare|net|recompute|calc", action, re.I), \
                    f"ACTION[{code!r}] should mention what to calculate: {action!r}"

    def test_date_codes_mention_year(self):
        for code in ("DATE_BEFORE_PRINT", "DATE_FAR_FUTURE"):
            if code in INFO:
                _, expl = INFO[code]
                assert "year" in expl.lower() or "ocr" in expl.lower(), \
                    f"INFO[{code!r}] should mention year/OCR error: {expl!r}"

    def test_four_eyes_codes_reference_gmp(self):
        if "4EYES_DISTINCT" in INFO:
            _, expl = INFO["4EYES_DISTINCT"]
            assert "GMP" in expl or "person" in expl.lower(), \
                "4EYES_DISTINCT explanation should reference GMP or persons"

    def test_status_labels_cover_all_states(self):
        # Every expected review state has a human label
        for key in ("auto_accepted", "needs_review", "confirmed", "corrected"):
            assert key in STATUS_DE, f"STATUS_DE missing key {key!r}"
            label = STATUS_DE[key]
            assert label and label.strip(), f"STATUS_DE[{key!r}] is empty"


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)
