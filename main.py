import os
import time
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import httpx
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://48fa-2800-e2-9a80-1a5-d97d-6dd1-ce60-8966.ngrok-free.app/auth/callback/")
SITE_ID = os.getenv("SITE_ID", "MCO")
ML_API_BASE = "https://api.mercadolibre.com"

# Verificar configuración
if not CLIENT_ID or not CLIENT_SECRET:
    print("⚠️ ADVERTENCIA: CLIENT_ID o CLIENT_SECRET no están configurados en el archivo .env")
    print("Por favor, crea un archivo .env con tus credenciales de Mercado Libre")

print(f"🔗 REDIRECT_URI configurado como: {REDIRECT_URI}")

# Almacena tokens en memoria (para demo)
_tokens = {"access_token": None, "refresh_token": None, "expires_at": 0}

# Modelos Pydantic
class Item(BaseModel):
    title: str
    price: float
    thumbnail: HttpUrl
    permalink: HttpUrl

class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[Item]

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    message: str = "Autenticación exitosa"

app = FastAPI(title="ML Colombia Proxy OAuth2")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todas las origenes en desarrollo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    """
    Endpoint raíz que proporciona información sobre la API
    """
    return {
        "app": "ML Colombia Proxy OAuth2",
        "version": "1.0.0",
        "endpoints": {
            "login": "/login/",
            "callback": "/auth/callback/",
            "search": "/search/"
        },
        "redirect_uri": REDIRECT_URI
    }

@app.get("/login/")
def login():
    """
    Redirige al usuario a MercadoLibre para autorizar la app.
    """
    auth_url = (
        f"https://auth.mercadolibre.com.co/authorization"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback/", response_model=TokenResponse)
async def auth_callback(code: str):
    """
    Recibe el `code`, lo intercambia por tokens y los almacena.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(
            status_code=500, 
            detail="CLIENT_ID o CLIENT_SECRET no configurados. Revise las variables de entorno."
        )
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ML_API_BASE}/oauth/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "authorization_code",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": REDIRECT_URI
                }
            )
        
        if resp.status_code != 200:
            error_detail = "Error desconocido"
            try:
                error_data = resp.json()
                error_detail = f"Error de Mercado Libre: {error_data}"
            except:
                error_detail = f"Error de Mercado Libre: {resp.text}"
                
            raise HTTPException(
                status_code=resp.status_code, 
                detail=error_detail
            )
        
        data = resp.json()
        _tokens.update({
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": time.time() + data["expires_in"] - 60
        })
        
        return {
            "access_token": data["access_token"],
            "token_type": data["token_type"],
            "expires_in": data["expires_in"],
            "refresh_token": data["refresh_token"]
        }
    
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al conectar con la API de Mercado Libre: {str(e)}"
        )

async def get_access_token() -> str:
    """
    Devuelve un access_token válido, renovándolo si expiró.
    """
    if not _tokens["access_token"]:
        raise HTTPException(
            status_code=401, 
            detail="No autenticado. Debe iniciar sesión primero usando /login/"
        )
    
    if time.time() >= _tokens["expires_at"]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{ML_API_BASE}/oauth/token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={
                        "grant_type": "refresh_token",
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "refresh_token": _tokens["refresh_token"]
                    }
                )
            
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Error al renovar token: {resp.json()}"
                )
            
            data = resp.json()
            _tokens.update({
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_at": time.time() + data["expires_in"] - 60
            })
        
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error de conexión al renovar token: {str(e)}"
            )
    
    return _tokens["access_token"]

@app.get("/search/", response_model=SearchResponse)
async def search_items(
    q: str = Query(..., min_length=1, description="Término de búsqueda"),
    limit: int = Query(10, ge=1, le=100, description="Número máximo de resultados"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
    token: str = Depends(get_access_token)
):
    """
    Busca productos en MercadoLibre Colombia usando `q` y retorna título,
    precio, imagen y enlace de cada uno.
    """
    try:
        url = f"{ML_API_BASE}/sites/{SITE_ID}/search"
        params = {"q": q, "limit": limit, "offset": offset}
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers)
        
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, 
                detail=f"Error de la API de MercadoLibre: {resp.json()}"
            )
        
        data = resp.json()
        items = [
            Item(
                title=e["title"],
                price=e["price"],
                thumbnail=e["thumbnail"],
                permalink=e["permalink"]
            ) for e in data.get("results", [])
            if all(k in e for k in ("title", "price", "thumbnail", "permalink"))
        ]
        
        return SearchResponse(
            query=q, 
            total=data["paging"]["total"], 
            results=items
        )
    
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al conectar con la API de MercadoLibre: {str(e)}"
        )

# Solo ejecutar si se ejecuta directamente
if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando servidor en http://localhost:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)