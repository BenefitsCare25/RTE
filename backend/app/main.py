from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import enrichment
import os

app = FastAPI(
    title="Company Data Enrichment API",
    description="API for enriching company data with contact information",
    version="1.0.0"
)

# CORS configuration
origins = [
    os.getenv("FRONTEND_URL", "http://localhost:5173"),
    "http://localhost:5173",
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(enrichment.router, prefix="/api", tags=["enrichment"])

@app.get("/")
async def root():
    return {
        "message": "Company Data Enrichment API",
        "status": "active",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
