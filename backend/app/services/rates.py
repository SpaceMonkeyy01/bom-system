"""Rate resolution: which price a BOM line uses for a material, per the rate policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, MaterialRate, RatePolicy
from app.models.core import RateSource


@dataclass
class ResolvedRate:
    rate: float
    source: str  # "bom" | "iflow:BS" | "iflow:NS" | "other" | "none"
    effective_from: date | None
    stale: bool
    policy_scope: str  # global | category | material
    uom: str | None = None  # the rate's UOM code (after conversion, the line's unit)
    uom_mismatch: bool = False  # True when no rate exists in the requested UOM and another was used
    converted_from: str | None = None  # e.g. "Quarter" when a per-quart rate was converted to per-gram


def _source_key(src: str) -> tuple[RateSource, str]:
    """"bom" | "iflow:BS" | "supplier" | "supplier:cheapest" | "supplier:<id>" -> (source, qualifier)."""
    if ":" in src:
        a, b = src.split(":", 1)
        return RateSource(a), b
    return RateSource(src), ""


class RateResolver:
    """Loads policies once and answers rate lookups for many materials (one BOM)."""

    def __init__(self, db: Session, as_of: date | None = None):
        self.db = db
        self.as_of = as_of or date.today()
        pols = list(db.scalars(select(RatePolicy)))
        self.global_policy = next((p for p in pols if p.scope == "global"), None)
        self.by_category = {p.scope_id: p for p in pols if p.scope == "category"}
        self.by_material = {p.scope_id: p for p in pols if p.scope == "material"}
        self._cache: dict[int, list[MaterialRate]] = {}
        self._conv_cache: dict[tuple, dict[int, float]] = {}

    def policy_for(self, material: Material) -> tuple[RatePolicy | None, str]:
        if material.id in self.by_material:
            return self.by_material[material.id], "material"
        cat = material.category
        while cat is not None:  # walk up the tree: a policy on "Paints" applies to "Paints / 2K Paint / Nexa"
            if cat.id in self.by_category:
                return self.by_category[cat.id], "category"
            cat = cat.parent
        return self.global_policy, "global"

    def rates_for(self, material_id: int) -> list[MaterialRate]:
        if material_id not in self._cache:
            self._cache[material_id] = list(
                self.db.scalars(
                    select(MaterialRate)
                    .where(MaterialRate.material_id == material_id, MaterialRate.effective_from <= self.as_of)
                    .order_by(MaterialRate.effective_from.desc(), MaterialRate.id.desc())
                )
            )
        return self._cache[material_id]

    def resolve(self, material: Material, uom_id: int | None = None) -> ResolvedRate:
        """Pick a rate. When `uom_id` is given (the template line's unit), rates in that unit are preferred;
        if none exists in any source, fall back to the policy order and flag the mismatch."""
        if uom_id is not None:
            r = self._resolve(material, lambda x: x.uom_id == uom_id)
            if r.source != "none":
                return r
            # no rate in the line's unit: accept rates we can convert (material-specific first, then generic)
            convertible = self._conversions_to(uom_id, material.id)
            r = self._resolve(material, lambda x: x.uom_id in convertible)
            if r.source != "none":
                from_code = r.uom
                r = self._apply_conversion(r, convertible, uom_id)
                r.converted_from = from_code
                return r
            r = self._resolve(material, lambda x: True)
            if r.source != "none" and r.uom and self._uom_code(uom_id) != r.uom:
                r.uom_mismatch = True
            return r
        return self._resolve(material, lambda x: True)

    def _conversions_to(self, to_uom_id: int, material_id: int) -> dict[int, float]:
        """{from_uom_id: factor} where qty_to = qty_from * factor. A rate per `from` unit becomes rate/factor per `to` unit."""
        from app.models import UOMConversion

        key = (to_uom_id, material_id)
        if key not in self._conv_cache:
            out: dict[int, float] = {}
            rows = list(self.db.scalars(select(UOMConversion).where(UOMConversion.to_uom_id == to_uom_id, (UOMConversion.material_id == material_id) | UOMConversion.material_id.is_(None))))
            # generic first, then material-specific overrides
            for c in sorted(rows, key=lambda c: 0 if c.material_id is None else 1):
                out[c.from_uom_id] = float(c.factor)
            # reverse direction of conversions declared the other way round
            rev = list(self.db.scalars(select(UOMConversion).where(UOMConversion.from_uom_id == to_uom_id, (UOMConversion.material_id == material_id) | UOMConversion.material_id.is_(None))))
            for c in sorted(rev, key=lambda c: 0 if c.material_id is None else 1):
                if float(c.factor):
                    out.setdefault(c.to_uom_id, 1.0 / float(c.factor))
            self._conv_cache[key] = out
        return self._conv_cache[key]

    def _apply_conversion(self, r: ResolvedRate, convertible: dict[int, float], to_uom_id: int) -> ResolvedRate:
        from app.models import UOM

        from_uom = self.db.scalar(select(UOM).where(UOM.code == r.uom))
        factor = convertible.get(from_uom.id if from_uom else -1)
        if factor:
            r.rate = round(r.rate / factor, 6)
            r.uom = self._uom_code(to_uom_id)
        return r

    def _uom_code(self, uom_id: int | None) -> str | None:
        if uom_id is None:
            return None
        from app.models import UOM

        u = self.db.get(UOM, uom_id)
        return u.code if u else None

    def _resolve(self, material: Material, accept) -> ResolvedRate:
        policy, scope = self.policy_for(material)
        order: list[str] = []
        if policy:
            order.append(policy.preferred_source.value)
            order += [s for s in (policy.fallback_order or []) if s not in order]
        else:
            order = ["bom", "iflow:BS", "iflow:NS"]
        staleness = policy.staleness_days if policy else 60
        rates = [x for x in self.rates_for(material.id) if accept(x)]
        for src in order:
            source, qualifier = _source_key(src)
            if source == RateSource.supplier:
                r = self._pick_supplier_rate(material, rates, qualifier or (policy.supplier_rule if policy else "latest"))
            else:
                r = next((x for x in rates if x.source == source and (not qualifier or x.store == qualifier)), None)
            if r is not None:
                age = (self.as_of - r.effective_from).days
                if r.source == RateSource.supplier:
                    label = f"supplier:{r.supplier.name if r.supplier else r.supplier_id}"
                else:
                    label = f"{r.source.value}:{r.store}" if r.store else r.source.value
                return ResolvedRate(float(r.rate), label, r.effective_from, age > staleness, scope, self._uom_code(r.uom_id))
        return ResolvedRate(0.0, "none", None, True, scope)

    @staticmethod
    def _pick_supplier_rate(material: Material, rates: list[MaterialRate], rule: str) -> MaterialRate | None:
        """rule: "latest" (newest across suppliers), "cheapest" (lowest among each supplier's latest),
        "preferred" (material.preferred_supplier_id), or a supplier id."""
        sup = [r for r in rates if r.source == RateSource.supplier]
        if not sup:
            return None
        latest_per_supplier: dict[int | None, MaterialRate] = {}
        for r in sup:  # rates are newest first
            latest_per_supplier.setdefault(r.supplier_id, r)
        if rule == "latest":
            return sup[0]
        if rule == "cheapest":
            return min(latest_per_supplier.values(), key=lambda r: float(r.rate))
        if rule == "preferred":
            return latest_per_supplier.get(material.preferred_supplier_id) or sup[0]
        if rule.isdigit():
            return latest_per_supplier.get(int(rule))
        return sup[0]

    def all_rates(self, material: Material) -> list[dict]:
        """Side-by-side view for the UI: latest rate per source/store."""
        seen: set[tuple] = set()
        out = []
        for r in self.rates_for(material.id):
            k = ("supplier", r.supplier_id) if r.source == RateSource.supplier else (r.source.value, r.store)
            if k in seen:
                continue
            seen.add(k)
            if r.source == RateSource.supplier:
                label = f"supplier:{r.supplier.name if r.supplier else r.supplier_id}"
            else:
                label = f"{r.source.value}:{r.store}" if r.store else r.source.value
            out.append({"source": label, "rate": float(r.rate), "effective_from": r.effective_from.isoformat(), "uom": self._uom_code(r.uom_id)})
        return out
