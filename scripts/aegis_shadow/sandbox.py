"""Mandatory filesystem isolation for native daily workers."""
from pathlib import Path
import shutil
import sys


def launcher():
    if sys.platform != "linux":
        raise RuntimeError("native worker isolation requires Linux with Bubblewrap; use a Linux VM or a WSL2 Linux checkout")
    executable = shutil.which("bwrap")
    if executable is None:
        raise RuntimeError("native worker isolation requires Bubblewrap on PATH and working Linux user namespaces")
    return Path(executable).resolve(strict=True)


def worker_command(executable, work, command):
    workspace = work.resolve(strict=True)
    if workspace.name != "work" or not any(
            parent.name == "unified" and parent.parent.name == ".aegis-local" for parent in workspace.parents):
        raise ValueError("sandbox requires a private unified attempt workspace")
    return [str(executable), "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
            "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--ro-bind", "/", "/",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run",
            "--bind", str(workspace), str(workspace), "--chdir", str(workspace), "--", *command]
