"""Create or update a user from the command line.
Usage: python scripts/create_user.py email name role [password]   (role: admin|template_owner|bom_editor|inventory_manager|viewer)"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.models.core import Role  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

email, name, role = sys.argv[1].lower(), sys.argv[2], Role(sys.argv[3])
password = sys.argv[4] if len(sys.argv) > 4 else getpass.getpass("Password: ")
db = SessionLocal()
u = db.scalar(select(User).where(User.email == email))
if not u:
    u = User(email=email, name=name)
    db.add(u)
u.name, u.role, u.active, u.password_hash = name, role, True, hash_password(password)
db.commit()
print(f"{'updated' if u.id else 'created'} {email} as {role.value}")
