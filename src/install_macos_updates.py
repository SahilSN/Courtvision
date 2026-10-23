"""Install the user's nightly Courtvision LaunchAgent (1 a.m. local Mac time)."""

import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys


LABEL = "com.courtvision.nightly-intelligence"
ROOT_DIR = Path(__file__).resolve().parents[1]


def build_launch_agent(root=ROOT_DIR):
    root = Path(root).resolve()
    runtime = root / "results" / ".runtime" / "nightly"
    return {
        "Label": LABEL,
        "ProgramArguments": [str(root / ".venv" / "bin" / "python"),
                             str(root / "src" / "run_nightly_intelligence.py"), "--scheduled"],
        "WorkingDirectory": str(root),
        "StartCalendarInterval": {"Hour": 1, "Minute": 0},
        "RunAtLoad": True,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONUNBUFFERED": "1",
        },
        "StandardOutPath": str(runtime / "launchd.log"),
        "StandardErrorPath": str(runtime / "launchd-error.log"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-now", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This installer is for macOS only.")
    definition = build_launch_agent()
    if not Path(definition["ProgramArguments"][0]).exists():
        parser.error("Courtvision's .venv Python interpreter is missing.")
    (ROOT_DIR / "results" / ".runtime" / "nightly").mkdir(parents=True, exist_ok=True)
    agents = Path.home() / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    target = agents / f"{LABEL}.plist"
    if target.exists() and plistlib.loads(target.read_bytes()).get("Label") != LABEL:
        parser.error("Existing LaunchAgent does not match Courtvision; refusing to overwrite.")
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    loaded = subprocess.run(["/bin/launchctl", "print", service], capture_output=True)
    if b"state = running" in loaded.stdout:
        parser.error("The nightly job is running; wait for it to finish before reinstalling.")
    target.write_bytes(plistlib.dumps(definition))
    if loaded.returncode == 0:
        subprocess.run(["/bin/launchctl", "bootout", service], check=True)
    subprocess.run(["/bin/launchctl", "bootstrap", domain, str(target)], check=True)
    subprocess.run(["/bin/launchctl", "enable", service], check=True)
    if args.run_now:
        # RunAtLoad already starts the initial catch-up check. Do not restart it.
        print("Initial catch-up check starts automatically when the agent is loaded.")
    print(f"Installed: {target}")
    print("Schedule: daily at 1:00 a.m. in the Mac's local timezone (no hourly runs).")
    print(f"Status: launchctl print {service}")


if __name__ == "__main__":
    main()
