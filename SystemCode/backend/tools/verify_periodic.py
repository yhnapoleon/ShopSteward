"""Own three local processes for B0-06 acceptance, restart them, then stop them.

Run from the repository: .venv/Scripts/python.exe backend/tools/verify_periodic.py
Requires migrated, configured development databases and unused ports 8000/8001.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def main():
    for port in (8000, 8001):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Port {port} is already occupied; no processes were stopped")
    process_rounds = []
    with TemporaryDirectory(prefix="shopsteward-b0-06-") as logs:
        for restart in (False, True):
            processes, streams = [], []
            try:
                for name, module, directory in (
                    ("simulator", "simulator", "simulation"),
                    ("api", "app", "backend"),
                    ("worker", "app.worker", "backend"),
                ):
                    stream = open(Path(logs) / f"{int(restart)}-{name}.log", "w", encoding="utf-8")
                    streams.append(stream)
                    processes.append(
                        subprocess.Popen(
                            [sys.executable, "-m", module],
                            cwd=ROOT / directory,
                            stdout=stream,
                            stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        )
                    )
                process_rounds.append([process.pid for process in processes])
                deadline = time.monotonic() + 30
                for port in (8001, 8000):
                    while True:
                        if any(process.poll() is not None for process in processes):
                            raise RuntimeError("An owned service exited before readiness")
                        try:
                            with urlopen(
                                f"http://127.0.0.1:{port}/health/ready", timeout=1
                            ) as response:
                                if response.status == 200:
                                    break
                        except (URLError, TimeoutError):
                            pass
                        if time.monotonic() > deadline:
                            raise RuntimeError(f"Service on {port} did not become ready")
                        time.sleep(0.2)
                command = [sys.executable, "-m", "app.smoke_periodic"]
                if restart:
                    command.append("--verify-restart")
                subprocess.run(command, cwd=ROOT / "backend", check=True, timeout=150)
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                for process in processes:
                    process.wait(timeout=15)
                for stream in streams:
                    stream.close()
    path = ROOT / "docs/api/b0-06-periodic-smoke-result.json"
    record = json.loads(path.read_text("utf-8"))
    record["owned_process_ids_before_and_after_restart"] = process_rounds
    record["owned_processes_stopped_after_acceptance"] = True
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("B0-06 separate-process automatic SC01 and restart verified; owned services stopped")


if __name__ == "__main__":
    main()
