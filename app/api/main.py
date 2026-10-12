from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.database import init_db
from api.rooms import router as rooms_router
from api.routes import router as auth_router
from api.invitations import router as invitations_router

PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"
STATIC_DIR = PUBLIC_DIR / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Auth System for Messanger", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_login_page():
    return FileResponse(PUBLIC_DIR / "login.html")


@app.get("/login", include_in_schema=False)
async def serve_login_file():
    return FileResponse(PUBLIC_DIR / "login.html")


@app.get("/profile", include_in_schema=False)
async def serve_profile_page():
    return FileResponse(PUBLIC_DIR / "profile.html")


@app.get("/dashboard", include_in_schema=False)

async def serve_dashboard_page():
    return FileResponse(PUBLIC_DIR / "dashboard.html")


@app.get("/room", include_in_schema=False)
async def serve_room_page():
    return FileResponse(PUBLIC_DIR / "room.html")


app.include_router(rooms_router)
app.include_router(auth_router)
app.include_router(invitations_router)  
