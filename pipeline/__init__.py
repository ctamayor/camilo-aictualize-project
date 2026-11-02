"""Deterministic parts of the observation pipeline. No model calls live here."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus"
OUT_DIR = ROOT / "out"
