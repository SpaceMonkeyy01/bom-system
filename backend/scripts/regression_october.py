"""Regression: replay every October order block from the Google Sheet through the formula engine.

For each block we translate the sheet's own cell formulas into the engine's formula language (parameter cells
become variables, references to other lines are inlined), evaluate with the block's parameter values and unit
costs, and compare every line's quantity and total plus the block total with the sheet's cached values.

This proves the engine reproduces the sheet's arithmetic on real orders. It does NOT compare the BOM_Check
templates with the sheet's recipes (those differ by design); that comparison is a template-owner decision.

Usage:  python scripts/regression_october.py [--sheet October-BOM-2026] [--limit N] [--verbose]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine.formula import FormulaError, LineSpec, ParamSpec, calculate  # noqa: E402

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "Bill_of_Materials__October-2026_to_Onward_.xlsx"
TOL_ABS, TOL_REL = 0.01, 1e-6

from app.seed.sheet_blocks import CELL, PARAM_LABELS, SUM_RANGE, Block, Line, col_idx, num, parse_blocks  # noqa: E402,F401

class Translator:
    """Excel cell formula (within one block) -> engine formula."""

    def __init__(self, block: Block):
        self.b = block
        self.line_by_row = {ln.row: ln for ln in block.lines}
        self.extra_consts: dict[str, float] = {}  # cells we could only resolve by cached value
        self.cache: dict[int, str] = {}
        self.depth = 0

    def translate(self, raw) -> str:
        if raw is None or raw == "":
            return "0"
        if isinstance(raw, (int, float)):
            return repr(float(raw))
        s = str(raw).strip()
        if not s.startswith("="):
            return repr(float(s.replace(",", ""))) if num(s) is not None else "0"
        s = s[1:]
        s = re.sub(r"(\d+(?:\.\d+)?)%", lambda m: f"({m.group(1)}/100)", s)
        if re.search(r"!", s):
            raise FormulaError("references another sheet")
        if re.search(r"\b(SUMIF|VLOOKUP|SUM)\s*\(", s, re.I):
            raise FormulaError("aggregate function in a quantity")
        out = CELL.sub(self._ref, s)
        return out

    def _ref(self, m: re.Match) -> str:
        ref = f"{m.group(1)}{m.group(2)}"
        if ref in self.b.param_cells:
            return self.b.param_cells[ref][0]
        col, r = m.group(1), int(m.group(2))
        if col == "F" and r in self.line_by_row:
            if r in self.cache:
                return f"({self.cache[r]})"
            self.depth += 1
            if self.depth > 20:
                raise FormulaError("reference loop")
            try:
                inner = self.translate(self.line_by_row[r].qty_formula)
            finally:
                self.depth -= 1
            self.cache[r] = inner
            return f"({inner})"
        # anything else: a cell outside the parameter row whose cached value we take as a constant
        name = f"cell_{ref}"
        self.extra_consts[name] = ref
        return name


def replay_block(block: Block, values_lookup) -> dict:
    tr = Translator(block)
    params = []
    raw_inputs = {}
    numeric_vars = {}
    for p, v in block.param_cells.values():
        is_text = isinstance(v, str) and num(v) is None
        if is_text:
            params.append(ParamSpec(p, "select"))
            raw_inputs[p] = v
        else:
            # numeric parameters go in as plain variables: the sheet sometimes holds negative values
            # (e.g. Surface Area = -F43 to cancel paint), which the app's input validation would reject
            numeric_vars[p] = num(v) if v is not None else 0.0
    specs: list[LineSpec] = []
    misc_lines: dict[int, tuple[int, int, float]] = {}
    untranslated: list[tuple[str, str]] = []
    for idx, ln in enumerate(block.lines):
        uc_raw = ln.unit_cost_raw
        unit_cost: float | str | None = ln.unit_cost_value
        if isinstance(uc_raw, str) and SUM_RANGE.match(uc_raw):
            mm = SUM_RANGE.match(uc_raw)
            k = mm.group(3)
            kf = float(k[:-1]) / 100 if k.endswith("%") else float(k)
            misc_lines[idx] = (int(mm.group(1)), int(mm.group(2)), kf)
        try:
            f = tr.translate(ln.qty_formula)
        except (FormulaError, ValueError) as e:
            untranslated.append((ln.name or "?", str(e)))
            f = repr(ln.qty_value or 0.0)
        specs.append(LineSpec(idx, ln.name or "?", f, unit_cost, ln.category))
    extra_vars = dict(numeric_vars)
    for name, ref in tr.extra_consts.items():
        v = values_lookup(block.sheet, ref)
        extra_vars[name] = v if isinstance(v, str) else (v or 0.0)
    res = calculate(params, specs, raw_inputs, extra_vars=extra_vars)
    out = {"order": block.order_code, "sign_type": block.canonical_sign_type or block.sign_type, "lines": len(block.lines), "untranslated": untranslated, "qty_mismatch": [], "total_mismatch": [], "errors": []}
    computed_totals: dict[int, float] = {}
    for idx, (ln, r) in enumerate(zip(block.lines, res.lines)):
        if r.error:
            out["errors"].append((ln.name, r.error))
            continue
        qty_ok = ln.qty_value is None and r.qty_final == 0 or (ln.qty_value is not None and abs(r.qty_final - ln.qty_value) <= max(TOL_ABS, TOL_REL * abs(ln.qty_value)))
        if not qty_ok:
            out["qty_mismatch"].append((ln.name, ln.qty_value, round(r.qty_final, 4)))
        computed_totals[ln.row] = r.total
    # misc-of-range unit costs: expected = sum(sheet totals in range) * k ; ours = sum(our totals) * k
    grand_ours = 0.0
    for idx, (ln, r) in enumerate(zip(block.lines, res.lines)):
        total = r.total
        if idx in misc_lines:
            a, b, k = misc_lines[idx]
            total = sum(v for rr, v in computed_totals.items() if a <= rr <= b) * k * (r.qty_final if r.qty_final else 1.0)
        grand_ours += total
        if ln.total_value is not None and abs(total - ln.total_value) > max(TOL_ABS, TOL_REL * abs(ln.total_value)):
            out["total_mismatch"].append((ln.name, ln.total_value, round(total, 2)))
    out["grand_sheet"] = block.total_value
    out["grand_ours"] = round(grand_ours, 2)
    out["grand_ok"] = block.total_value is None or abs(grand_ours - block.total_value) <= max(0.05, 1e-6 * abs(block.total_value))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default="October-BOM-2026")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    blocks = parse_blocks(RAW, args.sheet)
    if args.limit:
        blocks = blocks[: args.limit]
    wv = openpyxl.load_workbook(RAW, read_only=True, data_only=True)
    vcache: dict[str, list] = {}

    def values_lookup(sheet, ref):
        if sheet not in vcache:
            vcache[sheet] = [list(r) for r in wv[sheet].iter_rows(values_only=True)]
        m = CELL.match(ref)
        r, c = int(m.group(2)) - 1, col_idx(m.group(1))
        rows = vcache[sheet]
        v = rows[r][c] if r < len(rows) and c < len(rows[r]) else None
        return v if isinstance(v, str) else num(v)

    results = [replay_block(b, values_lookup) for b in blocks]
    ok = [r for r in results if r["grand_ok"] and not r["qty_mismatch"] and not r["errors"]]
    print(f"{args.sheet}: {len(blocks)} order blocks, {sum(r['lines'] for r in results)} lines")
    print(f"  exact match (every line qty + block total): {len(ok)}")
    print(f"  block total matches but some line differs:   {sum(1 for r in results if r['grand_ok'] and r not in ok)}")
    print(f"  block total differs:                          {sum(1 for r in results if not r['grand_ok'])}")
    print(f"  lines whose formula could not be translated:  {sum(len(r['untranslated']) for r in results)}")
    print(f"  engine errors:                                {sum(len(r['errors']) for r in results)}")
    by_type: dict[str, list[int]] = {}
    for r in results:
        t = by_type.setdefault(r["sign_type"] or "?", [0, 0])
        t[0] += 1
        t[1] += 1 if r["grand_ok"] else 0
    print("\n  by sign type (blocks, total-matching):")
    for k, (a, b) in sorted(by_type.items(), key=lambda kv: -kv[1][0])[:20]:
        print(f"    {k[:45]:45s} {a:3d} {b:3d}")
    bad = [r for r in results if not r["grand_ok"] or r["qty_mismatch"] or r["errors"] or r["untranslated"]]
    if args.verbose or len(bad) <= 15:
        for r in bad[:40]:
            print(f"\n  {r['order']} [{r['sign_type']}] sheet={r['grand_sheet']} ours={r['grand_ours']}")
            for k in ("untranslated", "errors", "qty_mismatch", "total_mismatch"):
                for item in r[k][:6]:
                    print(f"      {k}: {item}")


if __name__ == "__main__":
    main()
