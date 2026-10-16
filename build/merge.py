"""Concatenate the part files into a single C source.

Run:  python merge.py
"""
import io
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
PARTS = ["part5.c", "part6.c", "part7.c", "part8.c"]


def main() -> int:
    chunks = []

    for name in PARTS:
        path = HERE / name
        chunks.append(io.open(path, encoding="utf-8").read())

    source = "\n".join(chunks)

    target = HERE.parent / "src" / "film-halftone.c"
    io.open(target, "w", encoding="utf-8", newline="\n").write(source)

    print(f"merged {len(PARTS)} parts -> {target}")
    print(f"{len(source.splitlines())} lines, {len(source)} chars")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
