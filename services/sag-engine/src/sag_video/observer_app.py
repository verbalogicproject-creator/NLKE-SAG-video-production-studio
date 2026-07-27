from fastapi import FastAPI

from .models import ObservationResult, ObserverRequest
from .observer import observe_artifact


app = FastAPI(title="SAG Video Observer", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "artifact-frame-observer-v0.2"}


@app.post("/observe", response_model=ObservationResult)
def observe(request: ObserverRequest) -> ObservationResult:
    return observe_artifact(request.contract)
