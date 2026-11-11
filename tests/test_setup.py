"""Exercise the real Makefile with a local installer stub; no downloads."""

import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_setup_retries_failed_install_and_tracks_dependency_changes(tmp_path: Path) -> None:
    shutil.copyfile("Makefile", tmp_path / "Makefile")
    manifest = tmp_path / "pyproject.toml"
    shutil.copyfile("pyproject.toml", manifest)
    interpreter = tmp_path / "python-stub"
    interpreter.write_text(f"#!{sys.executable}\n" + '''
import pathlib, shutil, sys
args = sys.argv[1:]
if args[0] == "-c":
    exec(args[1])
elif args[:2] == ["-m", "venv"]:
    target = pathlib.Path(args[2]) / "bin" / "python"
    target.parent.mkdir(parents=True)
    shutil.copyfile(__file__, target)
    target.chmod(0o755)
elif args[:2] == ["-m", "pip"]:
    with open("install-attempts", "a") as log:
        log.write("install\\n")
    if not pathlib.Path("allow-install").exists():
        sys.exit("Simulated interrupted installation")
elif args[:2] in (["-m", "pytest"], ["-m", "uvicorn"]):
    pathlib.Path("last-command").write_text(args[1])
else:
    sys.exit("Unexpected interpreter invocation")
''')
    interpreter.chmod(0o755)

    def make(target: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["make", target, f"PYTHON={interpreter}"], cwd=tmp_path,
            capture_output=True, text=True, timeout=20,
        )

    first = make("test")
    assert first.returncode != 0
    assert "Simulated interrupted installation" in first.stderr
    assert (tmp_path / ".venv/bin/python").exists()
    stamp = tmp_path / ".venv/.dependencies-installed"
    assert not stamp.exists()
    assert not (tmp_path / "last-command").exists()

    (tmp_path / "allow-install").touch()
    retry = make("test")
    assert retry.returncode == 0, retry.stderr
    assert stamp.exists()
    assert (tmp_path / "install-attempts").read_text().splitlines() == ["install", "install"]
    assert (tmp_path / "last-command").read_text() == "pytest"

    # Starting after successful setup must not install again.
    start = make("start")
    assert start.returncode == 0, start.stderr
    assert (tmp_path / "last-command").read_text() == "uvicorn"
    assert len((tmp_path / "install-attempts").read_text().splitlines()) == 2

    # A manifest change must invalidate the success marker, including on retry.
    older = manifest.stat().st_mtime - 2
    os.utime(stamp, (older, older))
    (tmp_path / "allow-install").unlink()
    failed_update = make("start")
    assert failed_update.returncode != 0
    (tmp_path / "allow-install").touch()
    updated = make("test")
    assert updated.returncode == 0, updated.stderr
    assert len((tmp_path / "install-attempts").read_text().splitlines()) == 4
