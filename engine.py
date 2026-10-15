"""KabadiLoop core engine: original logic, stdlib only (sqlite3).
Lifecycle state machine, hazard-aware routing, reuse matching,
batching, destination ranking, impact. Deterministic; no LLM math."""
import sqlite3, time

TRANSITIONS = {
    "scanned": {"assessed", "needs_verification"},
    "needs_verification": {"assessed", "specialist_handling"},
    "assessed": {"available_for_reuse", "recovery_inventory", "specialist_handling"},
    "available_for_reuse": {"matched", "recovery_inventory"},
    "matched": {"transfer_confirmed", "available_for_reuse"},
    "recovery_inventory": {"batched", "available_for_reuse"},
    "batched": {"handover_recorded", "recovery_inventory"},
    "handover_recorded": {"outcome_confirmed"},
    "specialist_handling": {"outcome_confirmed"},
    "transfer_confirmed": set(), "outcome_confirmed": set(),
}
HAZARDOUS = {"battery", "cell", "fluorescent tube", "e-waste", "paint", "medicine"}
# material -> (est. kg per item, INR/kg SAMPLE rate, recyclable)
MATERIALS = {"cardboard": (0.35, 8.0), "newspaper": (0.5, 12.0), "plastic": (0.03, 15.0),
             "glass": (0.25, 2.0), "aluminium": (0.015, 90.0), "clothes": (0.4, 5.0)}
CONF_MIN = 0.6
SCHEMA = """
CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, name TEXT NOT NULL, material TEXT,
 condition TEXT, confidence REAL, state TEXT NOT NULL DEFAULT 'scanned', batch_id INTEGER, locality TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id),
 prev_state TEXT, new_state TEXT NOT NULL, action TEXT, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS listings(id INTEGER PRIMARY KEY, item_id INTEGER UNIQUE REFERENCES items(id),
 status TEXT NOT NULL DEFAULT 'open', simulated INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, material TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'filling', destination TEXT);
"""

class RuleError(ValueError): pass

def connect(path=":memory:"):
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    db.executescript(SCHEMA); return db

def is_hazardous(name, material=None):
    t = f"{name} {material or ''}".lower()
    return any(h in t for h in HAZARDOUS)

def classify_decision(name, material, confidence):
    """Conservative routing: hazard or low confidence -> abstain/verify."""
    if is_hazardous(name, material):
        return "specialist_handling" if confidence >= CONF_MIN else "needs_verification"
    if confidence < CONF_MIN: return "needs_verification"
    return "assessed"

def add_item(db, name, material, confidence, condition="unknown", locality=None):
    cur = db.execute("INSERT INTO items(name,material,confidence,condition,locality) VALUES(?,?,?,?,?)",
                     (name, material, confidence, condition, locality))
    db.execute("INSERT INTO events(item_id,prev_state,new_state,action,ts) VALUES(?,?,?,?,?)",
               (cur.lastrowid, None, "scanned", "scan", time.time())); db.commit()
    return cur.lastrowid

def transition(db, item_id, new_state, action):
    row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row: raise RuleError(f"item {item_id} not found")
    if new_state not in TRANSITIONS.get(row["state"], set()):
        raise RuleError(f"invalid transition {row['state']} -> {new_state}")
    if is_hazardous(row["name"], row["material"]) and new_state in {
            "recovery_inventory", "batched", "available_for_reuse"}:
        raise RuleError("hazardous items cannot enter reuse or recyclable batches")
    db.execute("UPDATE items SET state=? WHERE id=?", (new_state, item_id))
    db.execute("INSERT INTO events(item_id,prev_state,new_state,action,ts) VALUES(?,?,?,?,?)",
               (item_id, row["state"], new_state, action, time.time())); db.commit()

def route(db, item_id):
    """Assess an item and move it to the state its decision requires."""
    r = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    d = classify_decision(r["name"], r["material"], r["confidence"] or 0)
    transition(db, item_id, d, "routing"); return d

# ---- reuse matching ----
COND = {"good": 1.0, "fair": 0.6, "poor": 0.2, "unknown": 0.3}
def score_match(offer, request):
    """offer: item dict; request: {want, locality, min_condition}. Returns (score, reasons)."""
    reasons, s = [], 0.0
    w = request["want"].lower()
    if w == offer["name"].lower(): s += 0.4; reasons.append("exact type match")
    elif w in offer["name"].lower() or (offer["material"] or "") in w: s += 0.2; reasons.append("related type/material")
    c = COND.get(offer["condition"], 0.3); s += 0.25 * c
    reasons.append(f"condition {offer['condition']}")
    if request.get("locality") and request["locality"] == offer["locality"]: s += 0.2; reasons.append("same locality")
    if c >= COND.get(request.get("min_condition", "fair"), 0.6): s += 0.15; reasons.append("meets minimum condition")
    return round(s, 3), reasons

def rank_matches(db, request):
    out = []
    for r in db.execute("SELECT * FROM items WHERE state='available_for_reuse'"):
        sc, why = score_match(dict(r), request)
        if sc >= 0.3: out.append({"item_id": r["id"], "score": sc, "why": why})
    return sorted(out, key=lambda m: -m["score"])

# ---- batching ----
def add_to_batch(db, item_id):
    r = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if r["material"] not in MATERIALS: raise RuleError("material not recyclable in MVP rules")
    b = db.execute("SELECT id FROM batches WHERE material=? AND status='filling'", (r["material"],)).fetchone()
    bid = b["id"] if b else db.execute("INSERT INTO batches(material) VALUES(?)", (r["material"],)).lastrowid
    transition(db, item_id, "batched", f"batch {bid}")
    db.execute("UPDATE items SET batch_id=? WHERE id=?", (bid, item_id)); db.commit(); return bid

def batch_totals(db, bid):
    b = db.execute("SELECT * FROM batches WHERE id=?", (bid,)).fetchone()
    n = db.execute("SELECT COUNT(*) FROM items WHERE batch_id=?", (bid,)).fetchone()[0]
    kg, rate = MATERIALS[b["material"]]
    return {"items": n, "est_kg": round(n * kg, 3), "est_value_inr": round(n * kg * rate, 2), "label": "estimate (sample rate)"}

SAMPLE_DESTINATIONS = [  # SIMULATED, not real facilities
    {"name": "Sample Kabadiwala A", "accepts": {"cardboard", "newspaper", "plastic"}, "min_kg": 2, "verified": False, "simulated": True},
    {"name": "Sample Recycler B", "accepts": {"cardboard", "glass", "aluminium"}, "min_kg": 5, "verified": True, "simulated": True},
]
def rank_destinations(material, est_kg, dests=SAMPLE_DESTINATIONS):
    out = []
    for d in dests:
        if material not in d["accepts"]: continue
        s = 0.5 + (0.3 if d["verified"] else 0) + (0.2 if est_kg >= d["min_kg"] else 0)
        out.append({**d, "score": s, "meets_min_qty": est_kg >= d["min_kg"]})
    return sorted(out, key=lambda d: -d["score"])

def handover(db, bid, destination):
    b = db.execute("SELECT * FROM batches WHERE id=?", (bid,)).fetchone()
    if b["status"] != "filling": raise RuleError("batch already handed over")
    for i in db.execute("SELECT id FROM items WHERE batch_id=?", (bid,)).fetchall():
        transition(db, i["id"], "handover_recorded", f"handover to {destination} (simulated)")
    db.execute("UPDATE batches SET status='handed_over', destination=? WHERE id=?", (destination, bid)); db.commit()

# ---- impact (deterministic, from records) ----
def impact(db):
    c = lambda st: db.execute("SELECT COUNT(*) FROM items WHERE state IN (%s)" % ",".join("?"*len(st)), st).fetchone()[0]
    total = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    final = c(["transfer_confirmed", "outcome_confirmed"])
    return {"total": total, "reused": c(["transfer_confirmed"]), "recycled_handover": c(["handover_recorded"]),
            "specialist": c(["specialist_handling"]), "pending_verification": c(["needs_verification"]),
            "confirmed_outcome_pct": round(100 * final / total, 1) if total else 0.0,
            "env_savings": None}  # omitted: no documented conversion factor yet
