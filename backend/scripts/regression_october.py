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

PARAM_LABELS = {
    "Crunched Area Backboard (Sqft)": "Backboard_Area",
    "Crunched Area Aluminum(ft2)": "Crunched_Area_Aluminum_ft2",
    "Crunched Area SS(ft2)": "Crunched_Area_SS_ft2",
    "Returns Alu(in)": "Returns_Alu_in",
    "Returns SS(in)": "Returns_SS_in",
    "LOC of Alu(Ft)": "LOC_of_Alu_Ft",
    "LOC of SS(Ft)": "LOC_of_SS_Ft",
    "Surface Area": "Surface_Area",
    "Number of Connections": "Number_of_Connections",
    "Finish": "Finish",
}

CELL = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")
SUM_RANGE = re.compile(r"^=?\s*sum\(\s*I(\d+)\s*:\s*I(\d+)\s*\)\s*\*\s*([0-9.]+%?)\s*$", re.I)


def col_idx(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


@dataclass
class Line:
    row: int
    category: str | None
    name: str | None
    qty_formula: str | None  # raw cell content (formula text or constant)
    qty_value: float | None  # cached
    unit_cost_raw: object
    unit_cost_value: float | None
    total_value: float | None


@dataclass
class Block:
    sheet: str
    header_row: int
    order_code: str | None
    sign_type: str | None
    canonical_sign_type: str | None
    param_cells: dict[str, tuple[str, object]]  # "F5" -> (param_name, value)
    lines: list[Line]
    total_value: float | None
    issues: list[str] = field(default_factory=list)


def num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def parse_blocks(path: Path, sheet: str) -> list[Block]:
    wf = openpyxl.load_workbook(path, read_only=True, data_only=False)[sheet]
    wv = openpyxl.load_workbook(path, read_only=True, data_only=True)[sheet]
    frows = [list(r) for r in wf.iter_rows(values_only=True)]
    vrows = [list(r) for r in wv.iter_rows(values_only=True)]
    blocks: list[Block] = []
    i = 0
    n = len(frows)

    def cell(rows, r, c):
        row = rows[r] if 0 <= r < len(rows) else []
        return row[c] if c < len(row) else None

    while i < n:
        row = vrows[i]
        if len(row) > 6 and row[4] == "Order Code" and row[6] == "Sign Type":
            h = i
            pr = h - 1
            params: dict[str, tuple[str, object]] = {}
            prow_v = vrows[pr] if pr >= 0 else []
            for c in range(len(prow_v)):
                label = prow_v[c]
                if isinstance(label, str) and label.strip() and not label.strip().startswith("Sign"):
                    pname = PARAM_LABELS.get(label.strip()) or ("Finish" if "finish" in label.lower() else re.sub(r"[^A-Za-z0-9]+", "_", re.sub(r"\(.*?\)", "", label)).strip("_") or "P")
                    if pname in {v[0] for v in params.values()}:
                        pname = pname + "_" + str(c)
                    # value sits in the next non-empty cell to the right (usually c+1, sometimes c+2)
                    def _is_label(k):
                        v = prow_v[k] if k < len(prow_v) else None
                        return isinstance(v, str) and (v.strip() in PARAM_LABELS or "(" in v or v.strip().lower().startswith(("loc", "returns", "crunched", "number", "finish", "surface")))

                    placed = False
                    for off in (1, 2):
                        k = c + off
                        if k < len(prow_v) and prow_v[k] not in (None, "") and not _is_label(k):
                            ref = f"{openpyxl.utils.get_column_letter(k + 1)}{pr + 1}"
                            params[ref] = (pname, prow_v[k])
                            placed = True
                            break
                        if _is_label(k):
                            break
                    if not placed:  # label present, value blank -> the cell right after the label, value 0
                        ref = f"{openpyxl.utils.get_column_letter(c + 2)}{pr + 1}"
                        params[ref] = (pname, None)
            lines: list[Line] = []
            j = h + 2
            total_value = None
            while j < n:
                fr, vr = frows[j], vrows[j]
                a = vr[0] if vr else None
                ival_f = cell(frows, j, 8)
                if isinstance(ival_f, str) and re.match(r"^=\s*sum\(", ival_f, re.I) and cell(vrows, j, 2) in (None, ""):
                    total_value = num(cell(vrows, j, 8))
                    j += 1
                    break
                if a == "Sign Type" or (len(vr) > 4 and vr[4] == "Order Code"):
                    break
                cat, name = cell(vrows, j, 2), cell(vrows, j, 3)
                if name not in (None, ""):
                    lines.append(
                        Line(
                            row=j + 1,
                            category=str(cat).strip() if cat else None,
                            name=str(name).strip(),
                            qty_formula=cell(frows, j, 5),
                            qty_value=num(cell(vrows, j, 5)),
                            unit_cost_raw=cell(frows, j, 7),
                            unit_cost_value=num(cell(vrows, j, 7)),
                            total_value=num(cell(vrows, j, 8)),
                        )
                    )
                j += 1
            # summary row: first column holds the canonical sign type
            canon = None
            for k in range(j, min(j + 4, n)):
                if cell(vrows, k, 0) == "Sign Type":
                    canon = cell(vrows, k + 1, 0)
                    break
            blocks.append(
                Block(
                    sheet=sheet,
                    header_row=h + 1,
                    order_code=str(row[5]).strip() if len(row) > 5 and row[5] not in (None, "") else None,
                    sign_type=str(row[7]).strip() if len(row) > 7 and row[7] else None,
                    canonical_sign_type=str(canon).strip() if canon else None,
                    param_cells=params,
                    lines=lines,
                    total_value=total_value,
                )
            )
            i = j
            continue
        i += 1
    return blocks


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
