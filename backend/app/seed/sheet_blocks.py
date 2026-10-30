"""Parse the Google Sheet's per-order BOM blocks (October tabs). Shared by the regression script and the
historical import."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

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
    order_date: object = None
    summary: dict[str, float] = field(default_factory=dict)  # the sheet's summary row: cost heads + total + W/H


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
            summary: dict[str, float] = {}
            for k in range(j, min(j + 4, n)):
                if cell(vrows, k, 0) == "Sign Type":
                    canon = cell(vrows, k + 1, 0)
                    hdr_row, val_row = vrows[k], vrows[k + 1] if k + 1 < n else []
                    for ci, label in enumerate(hdr_row):
                        if isinstance(label, str) and ci < len(val_row):
                            v = num(val_row[ci])
                            if v is not None:
                                summary[label.strip()] = v
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
                    order_date=row[3] if len(row) > 3 else None,
                    summary=summary,
                )
            )
            i = j
            continue
        i += 1
    return blocks


