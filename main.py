import os
import time
from typing import List
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl
import httpx
from dotenv import load_dotenv

# ── Carga de variables de entorno ─────────────────────────────
load_dotenv()
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI  = os.getenv("REDIRECT_URI")  # https://<tu-dominio>/auth/callback/
SITE_ID       = os.getenv("SITE_ID", "MCO")
ML_API_BASE   = "https://api.mercadolibre.com"

# ── Almacenamiento en memoria de tokens ────────────────────────
_tokens = {
    "access_token": None,
    "refresh_token": None,
    "expires_at": 0
}

# ── Modelos Pydantic ───────────────────────────────────────────
class Item(BaseModel):
    title: str
    price: float
    thumbnail: HttpUrl
    permalink: HttpUrl

class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[Item]

# ── App FastAPI ────────────────────────────────────────────────
app = FastAPI(title="ML Colombia Proxy OAuth2")

@app.get("/login/")
def login():
    # <-- Aquí usamos el endpoint regional de Colombia
    auth_url = (
        f"https://auth.mercadolibre.com.co/authorization"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback/")
async def auth_callback(code: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ML_API_BASE}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type":    "authorization_code",
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  REDIRECT_URI
            }
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=resp.json())
    data = resp.json()
    _tokens.update({
        "access_token":  data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at":    time.time() + data["expires_in"] - 60
    })
    return {"detail": "Autenticación exitosa"}

async def get_access_token() -> str:
    if not _tokens["access_token"]:
        raise HTTPException(status_code=401, detail="No autenticado")
    if time.time() >= _tokens["expires_at"]:
        # renovar
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ML_API_BASE}/oauth/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type":    "refresh_token",
                    "client_id":     CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "refresh_token": _tokens["refresh_token"]
                }
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Error al renovar token")
        data = resp.json()
        _tokens.update({
            "access_token":  data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at":    time.time() + data["expires_in"] - 60
        })
    return _tokens["access_token"]

@app.get("/search/", response_model=SearchResponse)
async def search_items(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    token: str = Depends(get_access_token)
):
    url = f"{ML_API_BASE}/sites/{SITE_ID}/search"
    params = {"q": q, "limit": limit, "offset": offset}
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.json())
    data = resp.json()
    items = [
        Item(
            title=e["title"],
            price=e["price"],
            thumbnail=e["thumbnail"],
            permalink=e["permalink"]
        )
        for e in data.get("results", [])
        if all(k in e for k in ("title","price","thumbnail","permalink"))
    ]
    return SearchResponse(query=q, total=data["paging"]["total"], results=items)
