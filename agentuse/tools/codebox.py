"""CodeBox — sandboxed execution of Python & JavaScript.

Runs untrusted code in a subprocess with CPU/memory/time limits and a
scrubbed environment. Output (stdout/stderr/exit code) streams to the grid.
"""
import asyncio
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .. import config


def _limits() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (12, 14))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    except Exception:
        pass


_SCRUB_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": str(config.SANDBOX),
    "TMPDIR": str(config.SANDBOX),
    "LANG": "C.UTF-8",
    "PYTHONUNBUFFERED": "1",
    "NO_COLOR": "1",
}


async def run_code(code: str, lang: str = "python", timeout: float = 12.0) -> dict:
    lang = lang.lower()
    if lang in ("py", "python", "python3"):
        cmd = [sys.executable, "-I", "{file}"]
        ext = ".py"
    elif lang in ("js", "javascript", "node"):
        node = None
        for cand in ("/usr/bin/node", "/usr/local/bin/node"):
            if os.path.exists(cand):
                node = cand
                break
        if not node:
            try:
                node = subprocess.run(["which", "node"], capture_output=True,
                                      text=True, timeout=5).stdout.strip()
            except Exception:
                node = ""
        if not node:
            return {"ok": False, "lang": "js", "error": "node runtime not found"}
        cmd = [node, "{file}"]
        ext = ".js"
    else:
        return {"ok": False, "lang": lang, "error": f"unsupported language '{lang}'"}

    fd, path = tempfile.mkstemp(suffix=ext, dir=str(config.SANDBOX), prefix="au_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        exe = [path if a == "{file}" else a for a in cmd]
        t0 = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *exe, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=str(config.SANDBOX), env=_SCRUB_ENV,
                preexec_fn=_limits)
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                killed = False
            except asyncio.TimeoutError:
                proc.kill()
                out, err = await proc.communicate()
                killed = True
        except Exception as e:
            return {"ok": False, "lang": lang, "error": f"{type(e).__name__}: {e}"}
        ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": not killed and proc.returncode == 0, "lang": lang,
                "exit": proc.returncode if not killed else -9,
                "killed": killed, "ms": ms,
                "stdout": out.decode("utf-8", "replace")[:20000],
                "stderr": err.decode("utf-8", "replace")[:8000]}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
