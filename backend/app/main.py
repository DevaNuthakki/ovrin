from fastapi import FastAPI
from app.routes import router

app = FastAPI(
    title="Ovrin API",
    description="GitHub-native speech AI regression debugging API for ASR evaluation.",
    version="0.1.0",
)

app.include_router(router)


@app.get("/")
def root():
    return {
        "message": "Ovrin backend is running",
        "version": "0.1.0",
    }