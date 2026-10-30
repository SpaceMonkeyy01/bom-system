"""SQLAlchemy models for the BOM system.

Design rules (see spec):
- Every entity has an app-generated integer id. External ids (Airtable, iFlow BS/NS, Odoo) live in
  MaterialExternalKey / Order.airtable_record_id, never as primary keys.
- Nothing referenced by a saved BOM is hard-deleted: rows carry `active` / `deleted_at` flags.
- Templates are versioned; BOMs point at the exact version and freeze every line.
"""

from .core import (  # noqa: F401
    AttributeDef,
    AttributeValue,
    Category,
    CostHead,
    Material,
    MaterialExternalKey,
    MaterialRate,
    RatePolicy,
    StockLine,
    StockSnapshot,
    UOM,
    User,
)
from .orders import BOM, BOMLine, Order, WriteBack  # noqa: F401
from .templates import ComponentLine, Parameter, SignType, Template  # noqa: F401
