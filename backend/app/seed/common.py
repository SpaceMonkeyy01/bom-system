"""Shared helpers for seed loaders."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UOM, CostHead, RatePolicy
from app.models.core import RateSource

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"

# ----------------------------------------------------------------------------- UOM

UOM_CANON: dict[str, list[str]] = {
    "Sqft": ["sqft", "sq ft", "sq.ft", "square feet", "ft2", "sft"],
    "Feet": ["feet", "ft", "foot", "rft", "running feet"],
    "Meter": ["meter", "meters", "m", "mtr", "metre"],
    "Inch": ["inch", "inches", "in"],
    "Piece": ["piece", "pieces", "pcs", "pc", "nos", "no", "number", "each", "unit"],
    "Set": ["set", "sets"],
    "Pair": ["pair", "pairs"],
    "Gram": ["gram", "grams", "g", "gm", "gms"],
    "Kg": ["kg", "kgs", "kilogram"],
    "Liter": ["liter", "litre", "liters", "litres", "ltr", "ltrs", "l"],
    "Quarter": ["quater", "quarter", "qtr", "qt"],
    "Gallon": ["gln", "gallon", "gallons", "gal"],
    "Roll": ["roll", "rolls"],
    "Box": ["box", "boxes"],
    "Packet": ["pkt", "packet", "pack", "pkts"],
    "Bottle": ["bottle", "bottles", "btl"],
    "Tube": ["tube", "tubes"],
    "Sheet": ["sheet", "sheets"],
    "Can": ["cane", "can", "tin"],
    "Coil": ["coil"],
    "Cylinder": ["cylinder"],
    "Ream": ["rim", "ream"],
    "CFT": ["cft", "cubic feet"],
    "Guz": ["guz", "gaz", "yard"],
    "Bundle": ["bundle", "bdl"],
    "Dozen": ["dozen", "dzn"],
    "Bag": ["bag", "bags"],
    "Drum": ["drum"],
    "Other": [],
}
_UOM_LOOKUP = {alias: code for code, aliases in UOM_CANON.items() for alias in aliases}
for _code in UOM_CANON:
    _UOM_LOOKUP[_code.lower()] = _code


def norm_uom(raw: str | None) -> str:
    t = re.sub(r"[^a-z0-9 .]", "", str(raw or "").strip().lower())
    t = re.sub(r"\s+", " ", t)
    if not t:
        return "Piece"
    return _UOM_LOOKUP.get(t) or _UOM_LOOKUP.get(t.rstrip("s")) or _UOM_LOOKUP.get(t.rstrip(".")) or "Other"


def ensure_uoms(db: Session) -> dict[str, UOM]:
    existing = {u.code: u for u in db.scalars(select(UOM))}
    for code, aliases in UOM_CANON.items():
        if code not in existing:
            u = UOM(code=code, name=code, aliases=aliases)
            db.add(u)
            existing[code] = u
    db.flush()
    return existing


# ----------------------------------------------------------------------------- names

_NAME_JUNK = re.compile(r"[^a-z0-9]+")


def loose_key(name: str | None) -> str:
    """Case/space/punctuation-insensitive key for matching free-text material names."""
    s = str(name or "").lower()
    s = s.replace("aluminum", "aluminium").replace("harnder", "hardner").replace("hardener", "hardner")
    s = re.sub(r"(\d)\s*g\b", r"\1g", s)  # "14 g" -> "14g"
    return _NAME_JUNK.sub("", s)


def clean(s) -> str | None:
    if s is None:
        return None
    t = re.sub(r"\s+", " ", str(s)).strip()
    return t or None


def to_float(v) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^0-9.\-]", "", str(v))
    try:
        return float(t) if t not in ("", "-", ".") else None
    except ValueError:
        return None


def to_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


# ----------------------------------------------------------------------------- cost heads

COST_HEADS: list[tuple[str, float, list[str]]] = [
    ("Metal", 20, ["metal", "stainless steel", "aluminium", "aluminum", "ms"]),
    ("Acrylic", 20, ["acrylic"]),
    ("LEDs", 0, ["led", "leds", "led strip", "led module", "neon"]),
    ("Paint", 0, ["paint", "primer", "thinner", "hardner"]),
    ("Power Supply", 0, ["power supply", "power supplies", "adopter", "adapter"]),
    ("Packaging", 0, ["packaging", "box", "packing"]),
    ("Misc", 0, ["misc", "miscellaneous", "hardware", "other"]),
    ("UV", 0, ["uv", "vinyl", "print", "ink"]),
    ("Alucobond", 10, ["alucobond", "acm"]),
    ("PVD Coating", 0, ["pvd", "pvd coating"]),
    ("Wires", 0, ["wire", "wires", "cord wire", "cable"]),
    ("Tanaka Nozzle", 0, ["tanaka nozzle", "tanka nozzle", "tanka", "welding"]),
]


def ensure_cost_heads(db: Session) -> dict[str, CostHead]:
    existing = {c.name: c for c in db.scalars(select(CostHead))}
    for i, (name, waste, aliases) in enumerate(COST_HEADS):
        if name not in existing:
            c = CostHead(name=name, sort_order=i, default_wastage_pct=waste, aliases=aliases)
            db.add(c)
            existing[name] = c
    db.flush()
    return existing


def ensure_default_rate_policy(db: Session) -> RatePolicy:
    pol = db.scalar(select(RatePolicy).where(RatePolicy.scope == "global"))
    if not pol:
        pol = RatePolicy(
            scope="global",
            scope_id=None,
            preferred_source=RateSource.bom,
            fallback_order=["iflow:BS", "iflow:NS"],
            staleness_days=60,
        )
        db.add(pol)
        db.flush()
    return pol


# category path -> cost head, used when a template line carries no cost tag
def cost_tag_for_category(path: str | None, name: str | None = None) -> str:
    p = (path or "").lower()
    n = (name or "").lower()
    if "tanka" in p or "tanka" in n or "tanaka" in n:
        return "Tanaka Nozzle"
    if "alucobond" in p or "alucobond" in n or "acm" in n.split():
        return "Alucobond"
    if p.startswith("metal works"):
        return "Metal"
    if p.startswith("acrylic"):
        return "Acrylic"
    if "power suppl" in p or "adopter" in p or "power supply" in n:
        return "Power Supply"
    if "wire" in p or p.endswith("/ wires") or "wire" in n:
        return "Wires"
    if p.startswith("electricals") or "led" in n or "neon" in p:
        return "LEDs"
    if p.startswith("paints") or p.startswith("epoxy"):
        return "Paint"
    if p.startswith("box & packaging"):
        return "Packaging"
    if p.startswith("paste & prints") or "uv" in n.split() or "vinyl" in n:
        return "UV"
    if "pvd" in n:
        return "PVD Coating"
    return "Misc"


GENERIC_CONVERSIONS = [  # (from, to, factor): qty_to = qty_from * factor
    ("Gallon", "Liter", 3.78541),
    ("Quarter", "Liter", 0.946353),
    ("Gallon", "Quarter", 4.0),
    ("Kg", "Gram", 1000.0),
    ("Meter", "Feet", 3.28084),
    ("Feet", "Inch", 12.0),
    ("Meter", "Inch", 39.3701),
]


def ensure_conversions(db: Session) -> int:
    from app.models import UOMConversion

    uoms = {u.code: u for u in db.scalars(select(UOM))}
    n = 0
    for f, t, k in GENERIC_CONVERSIONS:
        if f not in uoms or t not in uoms:
            continue
        exists = db.scalar(select(UOMConversion).where(UOMConversion.from_uom_id == uoms[f].id, UOMConversion.to_uom_id == uoms[t].id, UOMConversion.material_id.is_(None)))
        if not exists:
            db.add(UOMConversion(from_uom_id=uoms[f].id, to_uom_id=uoms[t].id, factor=k, note="generic"))
            n += 1
    db.flush()
    return n
