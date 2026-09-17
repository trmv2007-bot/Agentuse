"""Check the *interpreter-facing* contract of install.ps1's Python probe.

This does NOT run PowerShell (none is installed in this sandbox). It extracts
the $Probe string literal verbatim from install.ps1 and checks the two things
the installer depends on:

  A. a real Python 3.10+  -> prints its version on stdout, exits 0
  B. a Microsoft-Store-style stub (stderr message + non-zero exit) -> non-zero
  C. a too-old interpreter (reports 3.9, exits 1) -> non-zero
  D. the literal contains no double quote (PS 5.1 would mangle the argument)
"""
import os
import re
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "..", "install.ps1")

src = open(PS1, encoding="utf-8").read()
m = re.search(r"^\$Probe = '([^']+)'", src, re.M)
assert m, "could not find $Probe literal in install.ps1"
PROBE = m.group(1)
print(f"probe literal from install.ps1:\n  {PROBE}\n")

fails = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print("D. PS 5.1 argument-safety of the literal")
check("no embedded double quotes", '"' not in PROBE)
check("no embedded single quotes", "'" not in PROBE)
check("no $ (no PS interpolation surprises)", "$" not in PROBE)

print("\nA. real interpreter")
p = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True)
print(f"  stdout={p.stdout.strip()!r} stderr={p.stderr.strip()!r} exit={p.returncode}")
check("exits 0", p.returncode == 0)
ver = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
check("last stdout line looks like X.Y.Z", bool(re.fullmatch(r"\d+\.\d+\.\d+", ver)), ver)
check("matches running interpreter", ver == "%d.%d.%d" % sys.version_info[:3])

work = tempfile.mkdtemp(prefix="agentuse-stub-")

print("\nB. Microsoft Store stub (the exact message from the bug report)")
stub = os.path.join(work, "python")
with open(stub, "w") as fh:
    fh.write(
        "#!/bin/sh\n"
        'echo "Python was not found; run without arguments to install from the " >&2\n'
        'echo "Microsoft Store, or disable this shortcut from Settings > Apps > " >&2\n'
        'echo "Advanced app settings > App execution aliases." >&2\n'
        "exit 9009\n"   # the real stub returns 9009 (sh masks it to 49)
    )
os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
p = subprocess.run([stub, "-c", PROBE], capture_output=True, text=True)
print(f"  exit={p.returncode} first stderr line={p.stderr.splitlines()[0][:60]!r}")
check("exits non-zero -> candidate rejected", p.returncode != 0)
check("prints the stub message on stderr (installer can quote it back)",
      "Python was not found" in p.stderr)

print("\nC. too-old interpreter (reports 3.9.7, exits 1)")
old = os.path.join(work, "python3.9")
with open(old, "w") as fh:
    fh.write("#!/bin/sh\necho 3.9.7\nexit 1\n")
os.chmod(old, os.stat(old).st_mode | stat.S_IEXEC)
p = subprocess.run([old, "-c", PROBE], capture_output=True, text=True)
print(f"  exit={p.returncode} stdout={p.stdout.strip()!r}")
check("exits non-zero despite printing a version", p.returncode != 0,
      "the gate is the exit code, not the text")

print("\n" + ("ALL PASS" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
