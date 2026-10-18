"""Supervise actual FFmpeg compositions alongside MediaMTX; reap every stopped job."""
import json
import os
import subprocess
import time
import urllib.request


def get(url):
    with urllib.request.urlopen(url, timeout=1) as response:
        return json.load(response)


def supervise(media):
    jobs = {}
    try:
        while media.poll() is None:
            try:
                sessions = get("http://api:8080/internal/costreams")
                ready = {p["name"]: p for p in get("http://localhost:9997/v3/paths/list").get("items", []) if p.get("ready")}
                wanted = set()
                for state in sessions:
                    sid = state["session_id"]
                    inputs = [p for p in state["inputs"] if p["path"] in ready]
                    if state["layout"] == "spotlight":
                        inputs = inputs[:1]
                    if not inputs or state["status"] != "active":
                        continue
                    wanted.add(sid)
                    fingerprint = (state["layout"], tuple((p["path"], p.get("muted", False)) for p in inputs))
                    old = jobs.get(sid)
                    if old and old[0] == fingerprint and old[1].poll() is None:
                        continue
                    if old:
                        stop(old[1])
                    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
                    for item in inputs:
                        command += ["-rtsp_transport", "tcp", "-i", "rtsp://localhost:8554/" + item["path"]]
                    n = len(inputs)
                    filters = [f"[{i}:v]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]" for i in range(n)]
                    audio = []
                    for i, item in enumerate(inputs):
                        tracks = ready[item["path"]].get("tracks", [])
                        if any(t in ("MPEG4Audio", "Opus", "PCMU", "PCMA", "AAC") for t in tracks):
                            filters.append(f"[{i}:a]volume={0 if item.get('muted') else 1}[a{i}]")
                            audio.append(f"[a{i}]")
                    if audio:
                        filters.append("".join(audio) + f"amix=inputs={len(audio)}:duration=longest[aout]")
                    if n == 1 or state["layout"] == "spotlight":
                        filters.append("[v0]pad=1280:720:0:0[out]")
                    else:
                        positions = ["0_0", "640_0", "0_360", "640_360"][:n]
                        filters.append("".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={'|'.join(positions)}:fill=black,pad=1280:720:0:0[out]")
                    command += ["-filter_complex", ";".join(filters), "-map", "[out]"]
                    command += ["-map", "[aout]", "-c:a", "aac"] if audio else ["-an"]
                    command += ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-g", "24", "-pix_fmt", "yuv420p", "-f", "flv", f"rtmp://localhost:1935/costream/{sid}"]
                    jobs[sid] = (fingerprint, subprocess.Popen(command, start_new_session=True))
                for sid in list(jobs):
                    if sid not in wanted:
                        stop(jobs.pop(sid)[1])
            except Exception as exc:
                print("Compositor waiting:", type(exc).__name__, flush=True)
            time.sleep(.25)
    finally:
        for _, process in jobs.values():
            stop(process)


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    media = subprocess.Popen(["/mediamtx", "/mediamtx.yml"])
    try:
        supervise(media)
    finally:
        stop(media)
