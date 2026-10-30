"""暫存檔登記與定時清理。"""
import atexit
import os
import threading
import time

_tmp_lock = threading.Lock()
_tmp_paths: list[tuple[float, str]] = []   # (created_time, path)

def _reg_tmp(path: str) -> str:
    with _tmp_lock:
        _tmp_paths.append((time.time(), path))
    return path

def _sweep_tmp(max_age: float = 7200.0):
    cutoff = time.time() - max_age
    with _tmp_lock:
        survivors = []
        for ts, p in _tmp_paths:
            if ts < cutoff:
                try: os.remove(p)
                except OSError: pass
            else:
                survivors.append((ts, p))
        _tmp_paths[:] = survivors

@atexit.register
def _cleanup_all_tmp():
    with _tmp_lock:
        for _, p in _tmp_paths:
            try: os.remove(p)
            except OSError: pass

def _start_sweep_thread():
    def _loop():
        while True:
            time.sleep(3600)
            _sweep_tmp()
    t = threading.Thread(target=_loop, daemon=True)
    t.start()

_start_sweep_thread()
