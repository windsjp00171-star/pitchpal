import os
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from core import detect_key, transpose_audio, ALL_KEYS, capo_suggestions
from transcribe import transcribe_to_pdf
from jianpu import parse_and_synth, get_diatonic_chords, MELODY_KEYS

app = FastAPI(title="PitchPal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_upload(file: UploadFile) -> str:
    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(file.file.read())
    return path


@app.get("/api/keys")
def list_keys():
    return {"keys": ALL_KEYS}


@app.post("/api/detect")
async def detect(file: UploadFile = File(...)):
    path = _save_upload(file)
    try:
        result = detect_key(path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        os.remove(path)
    result["capo"] = capo_suggestions(result["key"])
    return result


@app.get("/api/capo/{key:path}")
def capo(key: str):
    return {"capo": capo_suggestions(key)}


@app.post("/api/transpose")
async def transpose(
    file: UploadFile = File(...),
    detected_key: str = Form(...),
    target_key: str = Form(...),
):
    path = _save_upload(file)
    try:
        out_path = transpose_audio(path, detected_key, target_key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.remove(path)

    return FileResponse(
        out_path,
        media_type="audio/wav",
        filename="transposed.wav",
        background=None,
    )


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    title: str = Form(""),
    composer: str = Form(""),
):
    path = _save_upload(file)
    try:
        pdf_path, msg = transcribe_to_pdf(path, title, composer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.remove(path)
    if pdf_path is None:
        raise HTTPException(status_code=422, detail=msg)
    return FileResponse(pdf_path, media_type="application/pdf", filename="score.pdf")


@app.get("/api/jianpu/keys")
def jianpu_keys():
    return {"keys": MELODY_KEYS}


@app.get("/api/jianpu/chords/{key}")
def diatonic_chords(key: str):
    return {"chords": get_diatonic_chords(key)}


@app.post("/api/jianpu/synth")
async def synth(
    melody: str = Form(""),
    chords: str = Form(""),
    key: str = Form("G"),
    bpm: int = Form(80),
    octave: int = Form(4),
    timbre: str = Form("鋼琴"),
    beats_per_bar: int = Form(4),
    metronome: bool = Form(False),
):
    if not melody.strip() and not chords.strip():
        raise HTTPException(status_code=422, detail="請輸入旋律或和弦。")
    try:
        out_path = parse_and_synth(
            melody, key, bpm, octave, timbre, chords, beats_per_bar, metronome
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return FileResponse(out_path, media_type="audio/wav", filename="preview.wav")


# 前端靜態檔（build 後）— 支援本機與 Docker 兩種路徑
_here = os.path.dirname(__file__)
for _candidate in [
    os.path.join(_here, "..", "frontend", "dist"),   # 本機開發
    "/app/frontend/dist",                             # Docker 絕對路徑
]:
    if os.path.exists(_candidate):
        app.mount("/", StaticFiles(directory=_candidate, html=True), name="static")
        break
