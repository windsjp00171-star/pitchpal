import os
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from core import detect_key, transpose_audio, ALL_KEYS

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
    return result


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


# 前端靜態檔（build 後）
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
