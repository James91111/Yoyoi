#!/usr/bin/env python3
"""Versi GitHub Actions dari transkrip_faster_whisper.py

Perbedaan penting vs versi terminal:
  * tanpa input() — semua konfigurasi dari environment variable
  * tanpa path absolut /root/storage — semua relatif ke workspace repo
  * mendukung SHARD (pecah pekerjaan ke beberapa job paralel)
  * hasil ditulis sebagai JSONL per-shard, digabung job "merge"

Env:
  LANG_CODE      en | id | auto            (default: auto)
  MODEL          small | base | medium ... (default: small)
  COMPUTE_TYPE   int8 (default)
  CPU_THREADS    thread per proses model   (default: 2)
  WORKERS        jumlah item paralel       (default: 1 — lihat catatan di README)
  SHARD_INDEX    mulai dari 0              (default: 0)
  SHARD_TOTAL    jumlah shard              (default: 1)
  AUDIO_DIR      folder audio              (default: whisper/input)
  META_FILE      metadata json opsional    (default: cari otomatis di AUDIO_DIR)
  OUT_FILE       file hasil                (default: whisper/output/shard.jsonl)
  DEMO           1 = buat audio demo sintetis kalau folder kosong
"""
import json
import os
import re
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import numpy as np

LANG_CODE = os.environ.get("LANG_CODE", "auto").strip().lower()
MODEL_NAME = os.environ.get("MODEL", "small")
COMPUTE_TYPE = os.environ.get("COMPUTE_TYPE", "int8")
CPU_THREADS = int(os.environ.get("CPU_THREADS", "2"))
WORKERS = int(os.environ.get("WORKERS", "1"))
SHARD_INDEX = int(os.environ.get("SHARD_INDEX", "0"))
SHARD_TOTAL = max(1, int(os.environ.get("SHARD_TOTAL", "1")))
AUDIO_DIR = os.environ.get("AUDIO_DIR", "whisper/input")
META_FILE = os.environ.get("META_FILE", "").strip()
OUT_FILE = os.environ.get("OUT_FILE", "whisper/output/shard.jsonl")
DEMO = os.environ.get("DEMO", "0") == "1"

AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus")
SR = 16_000


# ----------------------------------------------------------------------------
# 1. Kumpulkan daftar pekerjaan
# ----------------------------------------------------------------------------
def find_metadata():
    if META_FILE:
        return META_FILE if os.path.exists(META_FILE) else None
    for name in ("frame_metadata.json", "panelmetadata.json", "panel_metadata.json"):
        p = os.path.join(AUDIO_DIR, name)
        if os.path.exists(p):
            return p
    return None


def normalize(raw, mode):
    out = []
    for item in raw:
        if mode == "mode2":
            num = item.get("new_framenum", 0)
            audio = item.get("audio_file", f"frame{num:04d}.wav")
            start, end = item.get("starttime", 0.0), item.get("endtime", 0.0)
        else:
            num = item.get("panelnum", item.get("panel_num", 0))
            audio = item.get("audiofile", item.get("audio_file", f"panel{num:04d}.wav"))
            start = item.get("starttime", item.get("start_time", 0.0))
            end = item.get("endtime", item.get("end_time", 0.0))
        out.append({"item_num": num, "audio_filename": audio,
                    "start_time": start, "end_time": end, "_raw": item})
    return out


def scan_folder(folder):
    items = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(AUDIO_EXT):
            m = re.search(r"(\d+)", name)
            items.append({"item_num": int(m.group(1)) if m else 0,
                          "audio_filename": name,
                          "start_time": 0.0, "end_time": 0.0, "_raw": {}})
    items.sort(key=lambda x: x["item_num"])
    return items


def make_demo_clips(folder, n=6, seconds=15):
    """Audio sintetis — hanya untuk smoke test pipeline, bukan untuk transkrip nyata."""
    os.makedirs(folder, exist_ok=True)
    rng = np.random.default_rng(0)
    for i in range(n):
        p = os.path.join(folder, f"demo{i:04d}.wav")
        if os.path.exists(p):
            continue
        t = np.arange(SR * seconds) / SR
        sig = 0.05 * rng.standard_normal(t.size) + 0.2 * np.sin(2 * np.pi * 180 * t)
        pcm = (np.clip(sig, -1, 1) * 32767).astype("<i2")
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())


def build_items():
    if DEMO and (not os.path.isdir(AUDIO_DIR) or not any(
            f.lower().endswith(AUDIO_EXT) for f in os.listdir(AUDIO_DIR))):
        make_demo_clips(AUDIO_DIR)

    meta = find_metadata()
    items = []
    if meta:
        with open(meta, encoding="utf-8") as f:
            raw = json.load(f)
        mode = "mode2" if "frame" in os.path.basename(meta) else "mode1"
        items = normalize(raw, mode)
        if all(i["item_num"] == 0 for i in items):
            items = []
    if not items:
        if not os.path.isdir(AUDIO_DIR):
            print(f"[FATAL] folder audio tidak ada: {AUDIO_DIR}")
            sys.exit(2)
        items = scan_folder(AUDIO_DIR)
    return items


def resolve(audio_dir, filename, num):
    for cand in (filename, f"frame{num:04d}.wav", f"frame_{num:04d}.wav",
                 f"panel{num:04d}.wav", f"panel_{num:04d}.wav"):
        p = os.path.join(audio_dir, cand)
        if os.path.exists(p):
            return p
    return os.path.join(audio_dir, filename)


# ----------------------------------------------------------------------------
# 2. Transkripsi
# ----------------------------------------------------------------------------
def main():
    items = build_items()
    if not items:
        print("[FATAL] tidak ada audio ditemukan")
        sys.exit(2)

    my_items = [it for it in items if it["item_num"] % SHARD_TOTAL == SHARD_INDEX]
    print(f"total_item={len(items)} shard={SHARD_INDEX}/{SHARD_TOTAL} "
          f"item_shard_ini={len(my_items)} workers={WORKERS} cpu_threads={CPU_THREADS} "
          f"model={MODEL_NAME} compute={COMPUTE_TYPE} lang={LANG_CODE}")

    from faster_whisper import WhisperModel
    t0 = time.perf_counter()
    model = WhisperModel(MODEL_NAME, device="cpu", compute_type=COMPUTE_TYPE,
                         cpu_threads=CPU_THREADS)
    print(f"model_load={time.perf_counter() - t0:.2f}s")

    lang = None if LANG_CODE == "auto" else LANG_CODE

    def work(item):
        num = item["item_num"]
        path = resolve(AUDIO_DIR, item["audio_filename"], num)
        try:
            segs, _info = model.transcribe(path, language=lang, beam_size=1,
                                           vad_filter=False)
            text = " ".join(s.text for s in segs).strip()
        except Exception as e:                                  # noqa: BLE001
            text = f"[error: {e}]"
        return {"item_num": num, "audio": os.path.basename(path), "narasi": text}

    os.makedirs(os.path.dirname(OUT_FILE) or ".", exist_ok=True)
    t0 = time.perf_counter()
    rows = []
    if WORKERS <= 1:
        for i, item in enumerate(my_items, 1):
            rows.append(work(item))
            print(f"  [{i}/{len(my_items)}] item {item['item_num']} ok")
    else:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for i, row in enumerate(ex.map(work, my_items), 1):
                rows.append(row)
                print(f"  [{i}/{len(my_items)}] item {row['item_num']} ok")
    elapsed = time.perf_counter() - t0

    rows.sort(key=lambda r: r["item_num"])
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    per_item = elapsed / max(1, len(rows))
    print(f"selesai shard {SHARD_INDEX}: {len(rows)} item dalam {elapsed:.1f}s "
          f"({per_item:.2f}s/item) -> {OUT_FILE}")


if __name__ == "__main__":
    main()
