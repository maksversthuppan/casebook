from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, cases, clerks, courts, ingest, parties, record, refresh, search

# TEMPORARY - see app/api/debug_portal_probe.py's module docstring. Remove this
# import and its include_router call once the Render-portal-reachability
# question is answered.
from app.api import debug_portal_probe
from app.config import get_settings
from app.dcms import browser as dcms_browser
from app.dcms.session import registry as portal_sessions

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    # Advocates abandon half-finished refreshes and servers get restarted.
    # Neither may leave a browser behind.
    await portal_sessions.shutdown()
    await dcms_browser.shutdown()


app = FastAPI(
    title="Case Repository",
    version="0.1.0",
    description=(
        "The firm's record of its cases. DCMS is an outside reference consulted "
        "on demand, one case at a time, with an advocate solving the CAPTCHA."
    ),
    lifespan=lifespan,
)

# Added first, so it sits inside CORS and preflight is answered before sessions.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=not settings.debug,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(courts.router, prefix="/api")
app.include_router(parties.router, prefix="/api")
app.include_router(clerks.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(record.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(refresh.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(debug_portal_probe.router, prefix="/api")


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
