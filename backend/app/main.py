import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import applications, auth, automation, companies, gmail, insights, jobs, profile
from app.core.config import settings
from app.core.logging import setup_logging
from app.services import scheduler

setup_logging()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.APP_ENV == "production" and settings.SECRET_KEY.startswith("dev-insecure"):
        raise RuntimeError("Set SECRET_KEY in production")
    if settings.SCHEDULER_ENABLED:
        scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="JobHunter AI", version="1.0.0", lifespan=lifespan,
              description="AI-powered job hunting assistant for Riyadh & Jeddah")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


for r in (auth.router, profile.router, companies.router, jobs.router, applications.router, gmail.router,
          insights.router, automation.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
