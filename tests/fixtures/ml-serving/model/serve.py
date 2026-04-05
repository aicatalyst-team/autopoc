"""Model inference server using FastAPI and PyTorch."""

import torch
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class PredictRequest(BaseModel):
    text: str


class PredictResponse(BaseModel):
    prediction: float
    confidence: float


# Load model at startup
model = None


@app.on_event("startup")
def load_model():
    global model
    model = torch.load("model/model_weights.pt", map_location="cpu")
    model.eval()


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    # Dummy prediction
    return PredictResponse(prediction=0.95, confidence=0.87)


@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": model is not None}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
