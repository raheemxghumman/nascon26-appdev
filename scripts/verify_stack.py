"""Fail on missing live infrastructure; never substitutes mock readiness responses."""
import json
import urllib.request

with urllib.request.urlopen("http://localhost:8080/health", timeout=5) as response:
    assert json.load(response) == {"status": "ok"}
with urllib.request.urlopen("http://localhost:4444/status", timeout=5) as response:
    status = json.load(response)["value"]
    assert status["ready"] is True and len(status["nodes"]) >= 3
print("Backend healthy; three or more live Selenium nodes registered.")
