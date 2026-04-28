from fastapi import FastAPI
from api.routes.webhook import router as webhook_router

app = FastAPI()

app.include_router(webhook_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
