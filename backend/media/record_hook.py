"""Tell the API to upload each completed real recording segment to MinIO."""
import json
import os
import time
import urllib.request

payload = json.dumps({"path": os.environ.get("MTX_SEGMENT_PATH"), "stream": os.environ.get("MTX_PATH")}).encode()
for delay in (0, 0.2, 0.4):
    time.sleep(delay)
    try:
        request = urllib.request.Request("http://api:8080/internal/media/recording", data=payload,
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=5).close()
        break
    except Exception:
        if delay == 0.4:
            raise
