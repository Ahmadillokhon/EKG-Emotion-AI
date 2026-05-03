from fastapi import FastAPI, Request
import neurokit2 as nk
import joblib
import numpy as np
import os

app = FastAPI()

# AI Modelni yuklash
try:
    model = joblib.load('emotion_model.pkl')
except:
    model = None

@app.post("/predict")
async def predict_emotion(request: Request):
    data = await request.json()
    ekg_data = data.get("ekg", [])

    if len(ekg_data) < 100:
        return {"emotion": "Data short"}

    # Signalni tozalash va tahlil
    ekg_clean = nk.ecg_clean(ekg_data, sampling_rate=100)
    peaks, info = nk.ecg_peaks(ekg_clean, sampling_rate=100)
    hrv = nk.hrv_time(peaks, sampling_rate=100)

    # Emotsiyani aniqlash
    if model:
        features = np.array([[hrv['HRV_RMSSD'][0], hrv['HRV_MeanNN'][0]]])
        res = model.predict(features)[0]
    else:
        res = "Normal"

    return {"emotion": str(res), "status": "ok"}
