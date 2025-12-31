from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Autoriser toutes les origines (à sécuriser en production)
origins = [
    "http://localhost:3000",  # si tu utilises Flutter Web
    "*",  # autoriser toutes les origines pour le mobile
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # qui peut accéder
    allow_credentials=True,
    allow_methods=["*"],            # autorise GET, POST, OPTIONS, etc.
    allow_headers=["*"],            # autorise tous les headers
)

# Ajouter ton routeur
app.include_router(  )
