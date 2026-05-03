"""
EKG Emotion Monitor - FastAPI WebSocket Server
Ishlatish:
    pip install fastapi uvicorn websockets joblib neurokit2 scipy numpy
    python server.py
"""

import asyncio
import json
import numpy as np
import joblib
import neurokit2 as nk
from scipy.signal import butter, lfilter, iirnotch, lfilter_zi, resample
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from collections import deque
import uvicorn

# ── SOZLAMALAR ──────────────────────────────────────────
FS      = 200
ANALYZE = FS * 25   # 25 soniyalik signal
MODEL_PATH = "emotion_model.pkl"

EMOTIONS = {
    0: "NEYTRAL",
    1: "STRESS",
    2: "XOTIRJAM"
}

# ── MODEL ───────────────────────────────────────────────
try:
    model = joblib.load(MODEL_PATH)
    print(f"✅ Model yuklandi: {MODEL_PATH}")
except Exception as e:
    model = None
    print(f"⚠️  Model yuklanmadi: {e}")

# ── FILTRLAR ────────────────────────────────────────────
b_notch, a_notch = iirnotch(50.0, 30.0, FS)
b_bp, a_bp = butter(2, [0.5 / 100, 40.0 / 100], btype='band')

def make_filters():
    zi_notch = lfilter_zi(b_notch, a_notch) * 512.0
    zi_bp    = lfilter_zi(b_bp, a_bp) * 512.0
    return zi_notch, zi_bp

# ── APP ─────────────────────────────────────────────────
app = FastAPI()

# Static fayllar (HTML/CSS/JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# ── CONNECTED CLIENTS ────────────────────────────────────
browser_clients: list[WebSocket] = []
esp_client: WebSocket | None = None

async def broadcast(data: dict):
    """Barcha brauzerlarga yuborish"""
    msg = json.dumps(data)
    dead = []
    for client in browser_clients:
        try:
            await client.send_text(msg)
        except Exception:
            dead.append(client)
    for d in dead:
        browser_clients.remove(d)

# ── BRAUZER WEBSOCKET ────────────────────────────────────
@app.websocket("/ws")
async def ws_browser(websocket: WebSocket):
    await websocket.accept()
    browser_clients.append(websocket)
    print(f"🌐 Brauzer ulandi. Jami: {len(browser_clients)}")
    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            # Brauzerdan "analyze" buyrug'i kelsa ESP ga yuborish
            if data.get("type") == "analyze" and esp_client:
                try:
                    await esp_client.send_text(json.dumps({"cmd": "analyze"}))
                except Exception:
                    pass
    except WebSocketDisconnect:
        browser_clients.remove(websocket)
        print(f"🌐 Brauzer uzildi. Qolgan: {len(browser_clients)}")

# ── ESP32 WEBSOCKET ──────────────────────────────────────
@app.websocket("/esp")
async def ws_esp(websocket: WebSocket):
    global esp_client
    await websocket.accept()
    esp_client = websocket
    print("📡 ESP32 ulandi!")

    # Har ESP uchun alohida buferlar
    analyze_buf = []
    zi_notch, zi_bp = make_filters()
    manual_analyze = False

    async def send_status(text: str):
        await broadcast({"type": "status", "text": text})

    await send_status("QURILMA ULANDI")

    try:
        while True:
            raw = await websocket.receive_text()
            raw = raw.strip()

            # Brauzerdan kelgan "analyze" buyrug'i
            if raw == "ANALYZE":
                manual_analyze = True
                continue

            # Raqam bo'lsa signal sifatida qabul qilish
            try:
                val = int(raw)
            except ValueError:
                continue

            # Online filter
            y_n, zi_notch = lfilter(b_notch, a_notch, [float(val)], zi=zi_notch)
            y_b, zi_bp    = lfilter(b_bp, a_bp, y_n, zi=zi_bp)
            filtered = float(y_b[0])

            analyze_buf.append(filtered)

            # Brauzerlarga sample yuborish
            await broadcast({"type": "sample", "value": filtered})

            # 25 soniyada yoki qo'lda tahlil
            if len(analyze_buf) >= ANALYZE or (manual_analyze and len(analyze_buf) >= FS * 10):
                result = await asyncio.get_event_loop().run_in_executor(
                    None, analyze_signal, analyze_buf.copy()
                )
                if result:
                    await broadcast(result)
                analyze_buf.clear()
                manual_analyze = False

    except WebSocketDisconnect:
        esp_client = None
        await broadcast({"type": "status", "text": "QURILMA UZILDI"})
        print("📡 ESP32 uzildi")

# ── TAHLIL FUNKSIYASI ────────────────────────────────────
def analyze_signal(buf: list) -> dict | None:
    try:
        signal = np.array(buf)
        signal_700 = resample(signal, len(signal) * 700 // FS)
        cleaned = nk.ecg_clean(signal_700, sampling_rate=700)
        peaks, info = nk.ecg_peaks(cleaned, sampling_rate=700)

        if len(info['ECG_R_Peaks']) < 10:
            print("⚠️  R-peak yetarli emas!")
            return None

        hrv    = nk.hrv_time(peaks, sampling_rate=700)
        bpm    = 60000 / hrv['HRV_MeanNN'].values[0]
        rmssd  = hrv['HRV_RMSSD'].values[0]
        sdnn   = hrv['HRV_SDNN'].values[0]
        pnn50  = hrv['HRV_pNN50'].values[0]
        meannn = hrv['HRV_MeanNN'].values[0]

        if model is None:
            pred = 0
        else:
            features = np.array([[bpm, rmssd, sdnn, pnn50, meannn]])
            pred = int(model.predict(features)[0])

        emotion = EMOTIONS.get(pred, "NEYTRAL")

        print(f"\n{'='*40}")
        print(f"  HOLAT   : {emotion}")
        print(f"  BPM     : {bpm:.1f}")
        print(f"  RMSSD   : {rmssd:.2f}")
        print(f"  SDNN    : {sdnn:.2f}")
        print(f"  pNN50   : {pnn50:.2f}")
        print(f"{'='*40}")

        return {
            "type":    "result",
            "emotion": emotion,
            "pred":    pred,
            "bpm":     round(bpm, 1),
            "rmssd":   round(rmssd, 2),
            "sdnn":    round(sdnn, 2),
            "pnn50":   round(pnn50, 2),
            "meannn":  round(meannn, 2),
        }

    except Exception as e:
        print(f"⚠️  Tahlil xatosi: {e}")
        return None

# ── RUN ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Server ishga tushmoqda: http://localhost:8000")
    print("📡 ESP32 ulanish: ws://localhost:8000/esp")
    print("🌐 Brauzer ulanish: ws://localhost:8000/ws")
    uvicorn.run(app, host="0.0.0.0", port=8000)
