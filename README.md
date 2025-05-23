# ML FastAPI OAuth2 Proxy

Servicio REST en FastAPI que busca productos en MercadoLibre Colombia usando OAuth2.

## Requisitos previos

- Python 3.9+
- Cuenta en MercadoLibre Developers (con Client ID y Secret)
- Redirect URI configurada:
  - `https://4762-2800-e2-9a80-1a5-d97d-6dd1-ce60-8966.ngrok-free.app/auth/callback/`
- ngrok instalado o `pyngrok`

## Instalación

1. Clona este repositorio:
   ```bash
   git clone <repo-url>
   cd ml_fastapi_oauth

2. Crea y activa virtualenv:

    python -m venv venv
    source venv/bin/activate  # o venv\\Scripts\\activate en Windows

3. Instala dependencias:

    pip install -r requirements.txt

4. Copia .env.example a .env y completa:

    CLIENT_ID=...
    CLIENT_SECRET=...
    REDIRECT_URI=...
    SITE_ID=MCO

#   B a c k _ B B B 3 6 0  
 