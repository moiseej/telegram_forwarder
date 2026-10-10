"""Repeatable setup, configuration, offline tests and bot startup."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(argv: list[str], task: str) -> None:
    logs = ROOT / "artifacts" / "pipeline-logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / f"{task}-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    with path.open("w", encoding="utf-8") as log:
        result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print(f"{task}: {'OK' if result.returncode == 0 else 'FAILED'}; log: {path}")
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=["setup", "configure", "test", "run"])
    task = parser.parse_args().task
    if task == "configure":
        target = ROOT / "config.yaml"
        if target.exists():
            parser.error("config.yaml already exists; edit it manually")
        shutil.copyfile(ROOT / "config.example.yaml", target)
        print(f"Created {target}; replace example IDs before startup")
        return
    if task == "setup":
        if not PYTHON.exists():
            venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
        run([str(PYTHON), "-m", "pip", "install", "-r", "requirements.txt"], task)
        return
    if not PYTHON.exists():
        parser.error("Run setup first")
    if task == "test":
        run([str(PYTHON), "-m", "unittest", "discover", "-s", "tests", "-v"], task)
    else:
        if not (ROOT / "config.yaml").exists():
            parser.error("Run configure first and edit config.yaml")
        raise SystemExit(subprocess.call([str(PYTHON), "main.py"], cwd=ROOT))


if __name__ == "__main__":
    main()
