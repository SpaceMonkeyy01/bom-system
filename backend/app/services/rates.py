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


def _source_key(src: str) -> tuple[RateSource, str]:
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

    def resolve(self, material: Material) -> ResolvedRate:
        policy, scope = self.policy_for(material)
        order: list[str] = []
        if policy:
            order.append(policy.preferred_source.value)
            order += [s for s in (policy.fallback_order or []) if s not in order]
        else:
            order = ["bom", "iflow:BS", "iflow:NS"]
        staleness = policy.staleness_days if policy else 60
        rates = self.rates_for(material.id)
        for src in order:
            source, store = _source_key(src)
            for r in rates:  # newest first
                if r.source == source and (not store or r.store == store):
                    age = (self.as_of - r.effective_from).days
                    label = f"{source.value}:{r.store}" if r.store else source.value
                    return ResolvedRate(float(r.rate), label, r.effective_from, age > staleness, scope)
        return ResolvedRate(0.0, "none", None, True, scope)

    def all_rates(self, material: Material) -> list[dict]:
        """Side-by-side view for the UI: latest rate per source/store."""
        seen: set[tuple] = set()
        out = []
        for r in self.rates_for(material.id):
            k = (r.source.value, r.store)
            if k in seen:
                continue
            seen.add(k)
            out.append({"source": f"{r.source.value}:{r.store}" if r.store else r.source.value, "rate": float(r.rate), "effective_from": r.effective_from.isoformat()})
        return out
