"""Thin FastAPI layer over engine.py. NOT RUN in the build sandbox (no network to install fastapi)."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import engine as e
app = FastAPI(title="KabadiLoop"); db = None
def get():
    global db
    if db is None: db = e.connect("kabadiloop.db")
    return db
class Scan(BaseModel):
    name: str; material: str | None = None
    confidence: float = Field(ge=0, le=1); condition: str = "unknown"; locality: str | None = None
@app.post("/items")
def create(s: Scan):
    i = e.add_item(get(), s.name, s.material, s.confidence, s.condition, s.locality)
    return {"id": i, "decision": e.route(get(), i)}
@app.post("/items/{i}/transition/{state}")
def move(i: int, state: str):
    try: e.transition(get(), i, state, "api")
    except e.RuleError as x: raise HTTPException(409, str(x))
    return {"ok": True}
@app.post("/items/{i}/batch")
def batch(i: int):
    try: return {"batch_id": e.add_to_batch(get(), i)}
    except e.RuleError as x: raise HTTPException(409, str(x))
@app.get("/impact")
def impact(): return e.impact(get())
