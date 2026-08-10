from contextlib import asynccontextmanager
from html import escape
import secrets

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.analytics_store import get_stats_snapshot
from app.config import get_settings
from app.database import init_db
from app.model_registry import import_all_models
from app.shortlink_store import record_shortlink_click, resolve_shortlink
from app.system_health import collect_health


security = HTTPBasic(auto_error=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import_all_models()
    await init_db()
    yield


app = FastAPI(title="AmazonDealsBot Web", version="1.0", lifespan=lifespan)


def require_admin(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    settings = get_settings()
    if not settings.web_enabled or not settings.web_admin_token:
        raise HTTPException(status_code=503, detail="Dashboard web disattivata.")
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticazione richiesta.",
            headers={"WWW-Authenticate": "Basic"},
        )
    expected = settings.web_admin_token.get_secret_value()
    ok_user = secrets.compare_digest(credentials.username, "admin")
    ok_pass = secrets.compare_digest(credentials.password, expected)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide.",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/healthz")
async def healthz():
    health = await collect_health()
    return {
        "ok": health.db_ok,
        "database": health.db_backend,
        "manual_scheduler": health.manual_scheduler_ok,
        "autopost_scheduler": health.autopost_scheduler_ok,
        "amazon_provider": health.amazon_provider,
    }


@app.get("/readyz")
async def readyz():
    health = await collect_health()
    if not health.db_ok or not health.amazon_configured:
        raise HTTPException(status_code=503, detail="Servizio non pronto.")
    return {"ready": True}


@app.get("/r/{code}")
async def redirect_shortlink(code: str, request: Request):
    link = await resolve_shortlink(code)
    if link is None:
        raise HTTPException(status_code=404, detail="Shortlink non trovato.")
    await record_shortlink_click(
        link.id,
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )
    return RedirectResponse(link.destination_url, status_code=302)


@app.get("/api/stats", dependencies=[Depends(require_admin)])
async def api_stats(period: str = Query("7d", pattern="^(today|7d|30d|all)$")):
    settings = get_settings()
    stats = await get_stats_snapshot(settings.admin_user_id, period=period)
    return {
        "period": stats.period_label,
        "published": stats.published_total,
        "published_autopost": stats.published_autopost,
        "published_manual": stats.published_manual,
        "published_scheduled": stats.published_scheduled,
        "scheduled_pending": stats.scheduled_pending,
        "scans": stats.scans,
        "products_analyzed": stats.offers_scanned,
        "valid_deals": stats.deals_valid,
        "duplicates": stats.duplicates_avoided,
        "queue": {"pending": stats.queue_pending, "approved": stats.queue_approved, "rejected": stats.queue_rejected, "failed": stats.queue_failed},
        "errors": stats.publish_errors + stats.scheduled_errors,
        "top_categories": stats.top_categories,
        "top_brands": stats.top_brands,
    }


@app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def dashboard(period: str = "7d"):
    settings = get_settings()
    stats = await get_stats_snapshot(settings.admin_user_id, period=period)
    recent = "".join(
        f"<li>{escape(item.published_at.strftime('%d/%m %H:%M'))} — "
        f"{escape(item.source)} — {escape(item.title or item.asin)}</li>"
        for item in stats.recent_publications[:15]
    ) or "<li>Nessuna pubblicazione.</li>"
    return HTMLResponse(f"""
<!doctype html><html lang='it'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>AmazonDealsBot</title>
<style>body{{font-family:system-ui;max-width:980px;margin:30px auto;padding:0 18px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}.card{{border:1px solid #ddd;border-radius:12px;padding:16px}}a{{margin-right:10px}}</style></head><body>
<h1>AmazonDealsBot</h1><p>Periodo: <b>{escape(stats.period_label)}</b></p>
<p><a href='?period=today'>Oggi</a><a href='?period=7d'>7 giorni</a><a href='?period=30d'>30 giorni</a><a href='?period=all'>Tutto</a></p>
<div class='grid'>
<div class='card'><b>Pubblicati</b><br>{stats.published_total}</div>
<div class='card'><b>Autopost</b><br>{stats.published_autopost}</div>
<div class='card'><b>Manuali</b><br>{stats.published_manual}</div>
<div class='card'><b>Programmati</b><br>{stats.published_scheduled}</div>
<div class='card'><b>Scansioni</b><br>{stats.scans}</div>
<div class='card'><b>Prodotti analizzati</b><br>{stats.offers_scanned}</div>
<div class='card'><b>Deal validi</b><br>{stats.deals_valid}</div>
<div class='card'><b>Duplicati</b><br>{stats.duplicates_avoided}</div>
<div class='card'><b>Errori</b><br>{stats.publish_errors + stats.scheduled_errors}</div>
</div><h2>Recenti</h2><ul>{recent}</ul>
</body></html>""")
