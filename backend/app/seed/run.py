"""Run all seed loaders in order.  Usage:  python -m app.seed.run [--only materials,templates,rates,stock,orders]"""

from __future__ import annotations

import argparse
import json
import time

from app.db import SessionLocal
from app.seed.common import ensure_cost_heads, ensure_default_rate_policy, ensure_uoms
from app.seed.materials import seed_materials, seed_suppliers
from app.seed.orders import seed_orders
from app.seed.rates_stock import seed_bom_rates, seed_stock
from app.seed.historical_boms import import_october_boms
from app.seed.templates import seed_sign_types_and_templates

STEPS = {
    "materials": seed_materials,
    "suppliers": seed_suppliers,
    "templates": seed_sign_types_and_templates,
    "rates": seed_bom_rates,
    "stock": seed_stock,
    "orders": seed_orders,
    "historical_boms": import_october_boms,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated subset of: " + ",".join(STEPS))
    args = ap.parse_args()
    steps = args.only.split(",") if args.only else list(STEPS)
    db = SessionLocal()
    try:
        ensure_uoms(db)
        ensure_cost_heads(db)
        ensure_default_rate_policy(db)
        db.commit()
        for name in steps:
            t0 = time.time()
            result = STEPS[name](db)
            db.commit()
            brief = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in (result or {}).items()}
            print(f"[{name}] {time.time() - t0:5.1f}s {json.dumps(brief)}")
            for k, v in (result or {}).items():
                if isinstance(v, (list, dict)) and v:
                    sample = list(v.items())[:10] if isinstance(v, dict) else v[:10]
                    print(f"    {k} (first 10): {sample}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
