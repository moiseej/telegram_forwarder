"""Check this Compose service without exposing container secrets or raw logs."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def docker(*args):
    result = subprocess.run(["docker", *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Docker status command failed")
    return result.stdout


def check():
    ids = docker("compose", "ps", "-q", "bot").split()
    if len(ids) != 1:
        raise RuntimeError("Expected one running bot container")
    container_id = ids[0]
    for _ in range(15):
        info = json.loads(docker("inspect", container_id))[0]
        if not info["State"]["Running"] or info["RestartCount"]:
            raise RuntimeError("Bot stopped or restarted; inspect local logs")
        # Python logging uses stderr; fetch both streams, without printing either.
        result = subprocess.run(["docker", "logs", "--tail", "60", container_id], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("Cannot read container readiness logs")
        logs = result.stdout + result.stderr
        if "Application started" in logs:
            if "Conflict" in logs or "ERROR" in logs or "Traceback" in logs:
                raise RuntimeError("Bot reports an error; inspect local logs")
            print(json.dumps({"name": info["Name"].lstrip("/"), "image": info["Config"]["Image"],
                              "running": True, "restarts": 0, "application_started": True}))
            return
        time.sleep(2)
    raise RuntimeError("Bot did not become ready within 30 seconds")


if __name__ == "__main__":
    try:
        check()
    except Exception as error:
        print(f"Container check failed: {error}", file=sys.stderr)
        sys.exit(1)
