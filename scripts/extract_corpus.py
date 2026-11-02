"""Extract the corpus from the assignment zip onto a Windows-safe filesystem.

The Enron maildir files are named with a trailing dot (``1.``, ``10.``, ...),
which Windows cannot create, so a normal unzip silently drops every message.
This writes each message as ``<name>.eml`` and records the original path in
``corpus/manifest.csv`` so citations can still name the raw file.

Usage: python scripts/extract_corpus.py <zip> [<out_dir>]
"""

import csv
import hashlib
import sys
import zipfile
from pathlib import Path, PurePosixPath

CORPUS_MARKER = "corpus/"


def safe_name(name: str) -> str:
    """Map a maildir filename to one Windows can store."""
    return name.rstrip(".") + ".eml"


def extract(zip_path: Path, out_dir: Path) -> list[dict]:
    rows = []
    out_root = out_dir.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or f"/{CORPUS_MARKER}" not in f"/{info.filename}":
                continue
            original = info.filename.split(CORPUS_MARKER, 1)[1]
            parts = PurePosixPath(original).parts
            if any(p in ("", "..") for p in parts):
                raise ValueError(f"unsafe path in zip: {info.filename}")

            target = out_root.joinpath(*parts[:-1], safe_name(parts[-1])).resolve()
            if out_root not in target.parents:
                raise ValueError(f"path escapes output dir: {info.filename}")

            data = zf.read(info)
            digest = hashlib.sha256(data).hexdigest()
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise FileExistsError(f"refusing to overwrite differing file: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

            rows.append({
                "original_path": original,
                "extracted_path": target.relative_to(out_root).as_posix(),
                "bytes": len(data),
                "sha256": digest,
            })
    rows.sort(key=lambda r: r["original_path"])
    return rows


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    zip_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) == 3 else Path(__file__).resolve().parent.parent / "corpus"

    rows = extract(zip_path, out_dir)
    with open(out_dir / "manifest.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["original_path", "extracted_path", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"extracted {len(rows)} messages to {out_dir}")


if __name__ == "__main__":
    main()
