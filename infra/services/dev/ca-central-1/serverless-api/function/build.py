#!/usr/bin/env python3
"""Rebuild function.zip from src/ reproducibly (fixed timestamps and permissions).

Run from any directory: python3 function/build.py. The ZIP is committed so the
repository visibly contains the deployable function; the local workflow uploads it
to the artifact bucket before the function is created.
"""
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "src"
TARGET = HERE / "function.zip"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def build(target=TARGET):
    files = sorted(path for path in SOURCE.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    if not files:
        raise SystemExit("No source files found in " + str(SOURCE))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(SOURCE).as_posix(), FIXED_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return target


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else TARGET))
