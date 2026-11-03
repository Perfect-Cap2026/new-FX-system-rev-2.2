from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import providers as P
from app import services
from app.core.config import get_settings
from app.core.security import create_token, current_user, hash_password, verify_password
from app.db import get_db
from app.engines import risk
from app.models import Alert, AnalysisSnapshot, JournalEntry, User, Watchlist
from app.providers.base import TIMEFRAMES, validate_symbol

router = APIRouter()


def sym(symbol: str) -> str:
    try:
        return validate_symbol(symbol)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


# ---------------------------------------------------------------- auth
class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


@router.post("/auth/register", tags=["auth"], status_code=201)
def register(body: Register, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Email already registered")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password))
    user.watchlists.append(Watchlist(name="Core", symbols=get_settings().watchlist))
    db.add(user)
    db.commit()
    return {"access_token": create_token(user.id), "token_type": "bearer"}


@router.post("/auth/login", tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": create_token(user.id), "token_type": "bearer"}


@router.get("/auth/me", tags=["auth"])
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "role": user.role}


# ---------------------------------------------------------------- market
@router.get("/market/quote", tags=["market"])
async def quote(symbols: str = Query(..., max_length=400), _: User = Depends(current_user)):
    out = []
    for s in [sym(x.strip()) for x in symbols.split(",") if x.strip()][:30]:
        df = await run_in_threadpool(P.bars, s, "1d", 5)
        if df.empty:
            out.append({"symbol": s, "error": "no data"})
            continue
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2]) if len(df) > 1 else float(df["close"].iloc[-1])
        out.append({"symbol": s, "price": last, "change": round(last / prev - 1, 5), "as_of": df.index[-1].isoformat()})
    return out


@router.get("/market/bars/{symbol}", tags=["market"])
async def get_bars(symbol: str, tf: str = "1d", limit: int = Query(300, le=1000), _: User = Depends(current_user)):
    if tf not in TIMEFRAMES:
        raise HTTPException(422, f"tf must be one of {sorted(TIMEFRAMES)}")
    df = await run_in_threadpool(P.bars, sym(symbol), tf, limit)
    if df.empty:
        raise HTTPException(404, "No data")
    return [{"t": ts.isoformat(), "o": r.open, "h": r.high, "l": r.low, "c": r.close, "v": r.volume}
            for ts, r in df.iterrows()]


@router.get("/market/sectors", tags=["market"])
async def get_sectors(_: User = Depends(current_user)):
    return await run_in_threadpool(services.sectors)


# ---------------------------------------------------------------- analysis
@router.get("/analysis/{symbol}", tags=["analysis"])
async def analysis(symbol: str, thesis: bool = True, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = sym(symbol)
    rep = await run_in_threadpool(services.analyze_symbol, s, thesis)
    if not rep:
        raise HTTPException(404, f"Not enough data for {s}")
    d = rep["decision"]
    db.add(AnalysisSnapshot(user_id=user.id, symbol=s, composite=d["composite"], confidence=d["confidence"],
                            action=d["action"], report={"decision": d, "trade_setup": rep["trade_setup"]}))
    db.commit()
    return rep


@router.get("/analysis/{symbol}/history", tags=["analysis"])
def analysis_history(symbol: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AnalysisSnapshot).where(AnalysisSnapshot.symbol == sym(symbol), AnalysisSnapshot.user_id == user.id)
                      .order_by(AnalysisSnapshot.created_at.desc()).limit(50)).all()
    return [{"t": r.created_at.isoformat(), "composite": r.composite, "confidence": r.confidence, "action": r.action} for r in rows]


class RiskReq(BaseModel):
    symbol: str
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    targets: list[float] = Field(min_length=1, max_length=5)
    equity: float | None = Field(None, gt=0)
    risk_pct: float | None = Field(None, gt=0, le=5)
    daily_pnl: float = 0.0
    peak_equity: float | None = None


@router.post("/analysis/risk", tags=["analysis"])
def risk_check(body: RiskReq, _: User = Depends(current_user)):
    s = get_settings()
    acct = risk.Account(body.equity or s.account_equity, body.risk_pct or s.risk_per_trade_pct, s.max_daily_loss_pct,
                        s.max_total_drawdown_pct, s.min_rr, body.daily_pnl, body.peak_equity)
    direction = "long" if body.targets[0] > body.entry else "short"
    if (direction == "long" and body.stop >= body.entry) or (direction == "short" and body.stop <= body.entry):
        raise HTTPException(422, "Stop must be on the opposite side of entry from the targets")
    r = abs(body.entry - body.stop)
    setup = {"direction": direction, "entry": body.entry, "stop": body.stop, "targets": body.targets,
             "rr": [round(abs(t - body.entry) / r, 2) for t in body.targets]}
    return risk.evaluate(sym(body.symbol), setup, acct) | {"setup": setup}


# ---------------------------------------------------------------- macro / intermarket / dashboard
@router.get("/macro/dashboard", tags=["macro"])
async def macro_dashboard(_: User = Depends(current_user)):
    snap = await run_in_threadpool(services.macro_snapshot)
    if not snap:
        raise HTTPException(503, "Macro data unavailable")
    return snap


@router.get("/intermarket", tags=["intermarket"])
async def intermarket_view(_: User = Depends(current_user)):
    return await run_in_threadpool(services.intermarket_overview)


@router.get("/dashboard", tags=["dashboard"])
async def dashboard(watchlist_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    wl = db.get(Watchlist, watchlist_id) if watchlist_id else (user.watchlists[0] if user.watchlists else None)
    if wl and wl.user_id != user.id:
        raise HTTPException(404, "Watchlist not found")
    symbols = wl.symbols if wl and wl.symbols else get_settings().watchlist
    return await run_in_threadpool(services.dashboard, symbols)


# ---------------------------------------------------------------- watchlists
class WatchlistIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    symbols: list[str] = Field(max_length=40)

    @field_validator("symbols")
    @classmethod
    def _v(cls, v):
        return [validate_symbol(s.strip()) for s in v if s.strip()]


@router.get("/watchlists", tags=["watchlists"])
def list_watchlists(user: User = Depends(current_user)):
    return [{"id": w.id, "name": w.name, "symbols": w.symbols} for w in user.watchlists]


@router.post("/watchlists", tags=["watchlists"], status_code=201)
def create_watchlist(body: WatchlistIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = Watchlist(user_id=user.id, name=body.name, symbols=body.symbols)
    db.add(w)
    db.commit()
    return {"id": w.id, "name": w.name, "symbols": w.symbols}


@router.put("/watchlists/{wid}", tags=["watchlists"])
def update_watchlist(wid: int, body: WatchlistIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.get(Watchlist, wid)
    if not w or w.user_id != user.id:
        raise HTTPException(404, "Not found")
    w.name, w.symbols = body.name, body.symbols
    db.commit()
    return {"id": w.id, "name": w.name, "symbols": w.symbols}


# ---------------------------------------------------------------- journal
class JournalIn(BaseModel):
    symbol: str
    direction: str = Field(pattern="^(long|short)$")
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    target: float | None = None
    exit: float | None = None
    size: float = Field(1.0, gt=0)
    setup_tag: str | None = Field(None, max_length=60)
    notes: str | None = Field(None, max_length=5000)


def _journal_out(j: JournalEntry) -> dict:
    return {c.name: getattr(j, c.name) for c in JournalEntry.__table__.columns if c.name != "user_id"}


def _r_multiple(j: JournalEntry) -> float | None:
    if j.exit is None:
        return None
    risk_u = abs(j.entry - j.stop)
    pnl_u = (j.exit - j.entry) if j.direction == "long" else (j.entry - j.exit)
    return round(pnl_u / risk_u, 2) if risk_u else None


@router.get("/journal", tags=["journal"])
def list_journal(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(JournalEntry).where(JournalEntry.user_id == user.id).order_by(JournalEntry.opened_at.desc())).all()
    closed = [r for r in rows if r.r_multiple is not None]
    wins = [r for r in closed if r.r_multiple > 0]
    stats = {"trades": len(rows), "closed": len(closed),
             "win_rate": round(len(wins) / len(closed), 3) if closed else None,
             "avg_r": round(sum(r.r_multiple for r in closed) / len(closed), 2) if closed else None,
             "total_r": round(sum(r.r_multiple for r in closed), 2) if closed else 0}
    return {"stats": stats, "entries": [_journal_out(r) for r in rows]}


@router.post("/journal", tags=["journal"], status_code=201)
def add_journal(body: JournalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = JournalEntry(user_id=user.id, **body.model_dump() | {"symbol": sym(body.symbol)})
    j.r_multiple = _r_multiple(j)
    if j.exit is not None:
        j.closed_at = datetime.now(timezone.utc)
    db.add(j)
    db.commit()
    return _journal_out(j)


@router.patch("/journal/{jid}/close", tags=["journal"])
def close_journal(jid: int, exit: float = Query(gt=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(JournalEntry, jid)
    if not j or j.user_id != user.id:
        raise HTTPException(404, "Not found")
    j.exit, j.closed_at = exit, datetime.now(timezone.utc)
    j.r_multiple = _r_multiple(j)
    db.commit()
    return _journal_out(j)


@router.delete("/journal/{jid}", tags=["journal"], status_code=204)
def delete_journal(jid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(JournalEntry, jid)
    if not j or j.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(j)
    db.commit()


# ---------------------------------------------------------------- alerts
class AlertIn(BaseModel):
    symbol: str
    condition: str = Field(pattern="^(above|below)$")
    level: float = Field(gt=0)
    note: str | None = Field(None, max_length=200)


@router.get("/alerts", tags=["alerts"])
async def list_alerts(evaluate: bool = True, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Alert).where(Alert.user_id == user.id).order_by(Alert.created_at.desc())).all()
    out = []
    for a in rows:
        item = {"id": a.id, "symbol": a.symbol, "condition": a.condition, "level": a.level, "note": a.note,
                "active": a.active, "triggered_at": a.triggered_at}
        if evaluate and a.active:
            df = await run_in_threadpool(P.bars, a.symbol, "1d", 2)
            if not df.empty:
                px = float(df["close"].iloc[-1])
                item["price"] = px
                if (a.condition == "above" and px >= a.level) or (a.condition == "below" and px <= a.level):
                    a.active, a.triggered_at = False, datetime.now(timezone.utc)
                    item |= {"active": False, "triggered_at": a.triggered_at}
        out.append(item)
    db.commit()
    return out


@router.post("/alerts", tags=["alerts"], status_code=201)
def add_alert(body: AlertIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = Alert(user_id=user.id, **body.model_dump() | {"symbol": sym(body.symbol)})
    db.add(a)
    db.commit()
    return {"id": a.id}


@router.delete("/alerts/{aid}", tags=["alerts"], status_code=204)
def delete_alert(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Alert, aid)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(a)
    db.commit()
