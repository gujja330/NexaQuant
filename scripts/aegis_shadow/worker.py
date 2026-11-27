"""Execute a single candidate engine with separate imports and write guards."""
import os
import json
from pathlib import Path
import runpy
import subprocess
import sys


_ROOT = Path(__file__).resolve().parents[2]


def install_boundary(root):
    root = root.resolve(strict=True)

    def check(value):
        if isinstance(value, int):
            return
        path = Path(os.fsdecode(value))
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise PermissionError(f"shadow stage write outside workspace: {path}")
        if resolved.exists() and resolved.is_file() and resolved.stat().st_nlink != 1:
            raise PermissionError(f"shadow stage cannot modify a hard-linked file: {path}")

    authorized_child = False

    def audit(event, args):
        if event == "open":
            path, _, flags = args
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                check(path)
            elif not isinstance(path, int) and Path(os.fsdecode(path)).name.lower().startswith(".env"):
                raise PermissionError("shadow stages cannot read dotenv credentials")
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime", "os.truncate"}:
            check(args[0])
            # Directory-relative mutations could bypass path resolution.
            dir_fd = {"os.remove": 1, "os.rmdir": 1, "os.mkdir": 2,
                      "os.chmod": 2, "os.utime": 3}.get(event)
            if dir_fd is not None and args[dir_fd] not in (None, -1):
                raise PermissionError("directory-relative shadow mutation denied")
        elif event == "os.rename":
            check(args[0])
            check(args[1])
            if any(fd not in (None, -1) for fd in args[2:]):
                raise PermissionError("directory-relative shadow rename denied")
        elif event in {"subprocess.Popen", "_winapi.CreateProcess"} and authorized_child:
            return
        elif event in {"os.link", "os.symlink", "subprocess.Popen", "os.system",
                       "os.exec", "os.spawn", "os.posix_spawn", "os.fork", "os.startfile",
                       "_winapi.CreateProcess"}:
            raise PermissionError(f"shadow stage operation denied: {event}")
        elif event == "socket.getaddrinfo":
            host = args[0]
            if isinstance(host, (bytes, str)):
                hostname = os.fsdecode(host).lower().rstrip(".")
                if hostname == "telegram.org" or hostname.endswith(".telegram.org"):
                    raise PermissionError("Telegram network access denied")

    sys.addaudithook(audit)
    original_run = subprocess.run

    def run_guarded(command, **kwargs):
        nonlocal authorized_child
        if (not isinstance(command, (list, tuple))
                or list(command[:3]) != [sys.executable, "-m", "backend.recommendation.ssot.run"]
                or set(kwargs) - {"cwd", "capture_output", "text", "encoding", "errors", "timeout"}
                or Path(kwargs.get("cwd", root)).resolve() != root):
            raise PermissionError("only the isolated SSoT producer can be started by a stage")
        invocation = [sys.executable, "-I", "-B", "-X", "utf8", str(root / "scripts/aegis_shadow/worker.py"),
                      *command[1:]]
        authorized_child = True
        try:
            return original_run(invocation, **kwargs)
        finally:
            authorized_child = False

    subprocess.run = run_guarded


def main():
    target, *args = sys.argv[1:]
    sys.path.insert(0, str(_ROOT))
    install_boundary(_ROOT)
    policy = os.environ.pop("AEGIS_SHADOW_PRICE_PROVIDER", None)
    if policy:
        from scripts.aegis_shadow.provider import install
        import atexit

        circuit = install(json.loads(policy))
        atexit.register(lambda: print(f"Private price provider counters: {json.dumps(circuit.counts, sort_keys=True)}"))
    if target == "-m":
        module, *args = args
        sys.argv = [module, *args]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    else:
        script = (_ROOT / target).resolve(strict=True)
        if not script.is_relative_to(_ROOT):
            raise ValueError("stage script must be inside the workspace")
        sys.path.insert(0, str(script.parent))
        sys.argv = [str(script), *args]
        runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
