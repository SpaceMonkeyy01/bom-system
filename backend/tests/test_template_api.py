"""Template editor flow through the API against the dev database (seeded + dev users)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import SignType, Template, User

client = TestClient(app)


def _login(email, pw):
    r = client.post("/api/auth/login", data={"username": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def owner():
    db = SessionLocal()
    ok = db.scalar(select(User).where(User.email == "ali.hassan@example.com")) is not None
    st = db.scalar(select(SignType).where(SignType.name == "Metal - With Backlit"))
    db.close()
    if not ok or st is None:
        pytest.skip("dev users / seeded templates missing")
    return _login("ali.hassan@example.com", "ali-dev-pass"), st.id


def _editable(t: dict) -> dict:
    keys_p = ("label", "param_name", "uom", "input_type", "options", "default_value", "default_from_order", "required")
    keys_l = ("material_id", "qty_formula", "unit_cost_formula", "uom", "usage", "cost_tag", "work_centre", "wastage_pct", "optional", "notes")
    return {
        "parameters": [{k: p[k] for k in keys_p} for p in t["parameters"]],
        "lines": [{**{k: ln[k] for k in keys_l}, "material_name_hint": ln["material_name"]} for ln in t["lines"]],
        "notes": "api test",
    }


def test_validate_catches_bad_formulas_and_names():
    body = {
        "parameters": [{"label": "Area", "param_name": "Bad Name", "input_type": "number"}, {"label": "Finish", "param_name": "Finish", "input_type": "select", "options": []}],
        "lines": [{"material_id": None, "qty_formula": "Area *", "cost_tag": None}, {"material_id": None, "qty_formula": 'QTY("Paint")', "cost_tag": "Paint", "optional": True}],
    }
    r = client.post("/api/templates/validate", json=body, headers=_login("viewer@example.com", "viewer-dev-pass"))
    assert r.status_code == 200
    msgs = " | ".join(p["message"] for p in r.json())
    assert "no spaces" in msgs and "no choices" in msgs and "No material" in msgs and "itself" in msgs


def test_draft_edit_publish_cycle(owner):
    h, st_id = owner
    # discard any leftover draft from a previous run
    for v in client.get(f"/api/sign-types/{st_id}/templates", headers=h).json():
        if v["status"] == "draft":
            client.delete(f"/api/templates/{v['id']}", headers=h)
    before = client.get("/api/sign-types", headers=h).json()
    pub_before = next(s for s in before if s["id"] == st_id)["published_template_id"]

    r = client.post("/api/templates/drafts", json={"sign_type_id": st_id}, headers=h)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "draft" and len(d["lines"]) >= 20
    assert client.post("/api/templates/drafts", json={"sign_type_id": st_id}, headers=h).status_code == 400  # one draft at a time

    body = _editable(d)
    body["lines"][0]["qty_formula"] = "Crunched_Area_SS_ft2 * 1.2 +"
    r = client.put(f"/api/templates/{d['id']}", json=body, headers=h)
    assert r.status_code == 200 and r.json()["problems"]
    assert client.post(f"/api/templates/{d['id']}/publish", headers=h).status_code == 422

    # pick a factor different from whatever the current published version has, so the diff is non-empty on reruns
    factor = 1.31 if d["lines"][0]["qty_formula"].strip().endswith("1.3") else 1.3
    body["lines"][0]["qty_formula"] = f"Crunched_Area_SS_ft2 * {factor}"
    assert client.put(f"/api/templates/{d['id']}", json=body, headers=h).json()["problems"] == []
    prev = client.post(f"/api/templates/{d['id']}/preview", json={"parameters": {"Crunched_Area_SS_ft2": 2}}, headers=h)
    assert prev.status_code == 200 and prev.json()["lines"][0]["qty_final"] == pytest.approx(2 * factor)
    # unsaved edits preview without touching the stored draft, and a viewer may preview too
    live = dict(body)
    live["lines"] = [dict(body["lines"][0], qty_formula="Crunched_Area_SS_ft2 * 10"), *body["lines"][1:]]
    vh = _login("viewer@example.com", "viewer-dev-pass")
    prev = client.post(f"/api/templates/{d['id']}/preview", json={"parameters": {"Crunched_Area_SS_ft2": 2}, "draft": live}, headers=vh)
    assert prev.status_code == 200, prev.text
    assert prev.json()["lines"][0]["qty_final"] == pytest.approx(20) and prev.json()["lines"][0]["material_name"] == d["lines"][0]["material_name"]
    stored = client.get(f"/api/templates/{d['id']}", headers=h).json()
    assert stored["lines"][0]["qty_formula"] == f"Crunched_Area_SS_ft2 * {factor}"  # untouched
    assert len(stored["lines"]) == len(d["lines"])

    r = client.post(f"/api/templates/{d['id']}/publish", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "published"
    after = client.get("/api/sign-types", headers=h).json()
    assert next(s for s in after if s["id"] == st_id)["published_template_id"] == d["id"]
    db = SessionLocal()
    assert db.get(Template, pub_before).status == "retired"
    db.close()
    diff = client.get(f"/api/templates/{pub_before}/diff/{d['id']}", headers=h).json()
    assert diff["lines_changed"] and not diff["lines_added"]
    assert diff["lines_changed"][0].split("|")[0] == d["lines"][0]["material_name"]  # keyed by name, not id


def test_viewer_cannot_edit_templates(owner):
    _, st_id = owner
    vh = _login("viewer@example.com", "viewer-dev-pass")
    assert client.post("/api/templates/drafts", json={"sign_type_id": st_id}, headers=vh).status_code == 403
    assert client.get("/api/templates/flagged", headers=vh).status_code == 200  # reading the to-do list is fine


def test_unmapped_and_alias_remap(owner):
    h, _ = owner
    um = client.get("/api/sign-types/unmapped", headers=h).json()
    assert isinstance(um, list)
    if not um:
        pytest.skip("nothing unmapped")
    name = um[0]["name"]
    sts = client.get("/api/sign-types", headers=h).json()
    tgt = next(s for s in sts if s["template_count"] > 0)
    r = client.patch(f"/api/sign-types/{tgt['id']}", json={"name": tgt["name"], "code": tgt["code"], "aliases": [*tgt["aliases"], name], "active": True}, headers=h)
    assert r.status_code == 200
    assert all(u["name"] != name for u in client.get("/api/sign-types/unmapped", headers=h).json())
    # undo so the dev data stays honest (alias and the orders it remapped)
    client.patch(f"/api/sign-types/{tgt['id']}", json={"name": tgt["name"], "code": tgt["code"], "aliases": tgt["aliases"], "active": True}, headers=h)
    from app.models import Order

    db = SessionLocal()
    for o in db.scalars(select(Order).where(Order.sign_type_raw == name, Order.sign_type_id == tgt["id"])):
        o.sign_type_id = None
    db.commit()
    db.close()
