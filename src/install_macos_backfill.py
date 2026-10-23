"""Install login/crash recovery for the finite historical backfill, not nightly updates."""

import os
from pathlib import Path
import plistlib
import subprocess
import sys

from install_macos_updates import build_launch_agent as nightly_agent
from update_intelligence import ROOT_DIR


LABEL = "com.courtvision.historical-backfill"


def build_launch_agent(root=ROOT_DIR):
    root = Path(root).resolve()
    agent = nightly_agent(root)
    agent.pop("StartCalendarInterval")
    agent.update(Label=LABEL,
                 ProgramArguments=[str(root / ".venv/bin/python"), str(root / "src/run_managed_backfill.py")],
                 KeepAlive={"SuccessfulExit": False}, ThrottleInterval=300)
    # Successful completion stops the finite task. Crash recovery is throttled;
    # source/upload retries inside the runner retain their own backoff.
    runtime = root / "results/player_intelligence/.runtime"
    agent.update(StandardOutPath=str(runtime / "launchd.log"),
                 StandardErrorPath=str(runtime / "launchd-error.log"))
    return agent


def main():
    if sys.platform != "darwin":
        raise SystemExit("This installer is for macOS only.")
    definition = build_launch_agent()
    if not Path(definition["ProgramArguments"][0]).exists():
        raise SystemExit("Courtvision's .venv Python interpreter is missing.")
    agents = Path.home() / "Library/LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    target = agents / f"{LABEL}.plist"
    if target.exists() and plistlib.loads(target.read_bytes()).get("Label") != LABEL:
        raise SystemExit("Refusing to overwrite an unrelated LaunchAgent.")
    service = f"gui/{os.getuid()}/{LABEL}"
    loaded = subprocess.run(["/bin/launchctl", "print", service], capture_output=True)
    if loaded.returncode == 0:
        raise SystemExit("Backfill agent already installed; stop/unload it before reinstalling.")
    (ROOT_DIR / "results/player_intelligence/.runtime").mkdir(parents=True, exist_ok=True)
    target.write_bytes(plistlib.dumps(definition))
    subprocess.run(["/bin/launchctl", "enable", service], check=True)
    subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)], check=True)
    print(f"Installed {target}. Resumes at login and after unsuccessful exits; stops on completion.")


if __name__ == "__main__":
    main()
