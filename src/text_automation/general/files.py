from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional

from PyPDF2 import PdfMerger


def _natural_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def merge_pdfs(
    input_dir: str | Path,
    output_file: str | Path,
    pattern: Optional[str] = None,
    explicit_files: Optional[Iterable[str | Path]] = None,
) -> Path:
    """
    Merge PDFs in a directory into a single output file.

    - If explicit_files is provided, merges in that order relative to input_dir.
    - Else, merges PDFs matching pattern (default: all *.pdf) sorted naturally.
    """
    src = Path(input_dir)
    dst = Path(output_file)
    dst.parent.mkdir(parents=True, exist_ok=True)

    merger = PdfMerger()
    try:
        if explicit_files is not None:
            files = [src / Path(f) for f in explicit_files]
        else:
            pat = pattern or "*.pdf"
            files = sorted(src.glob(pat), key=lambda p: _natural_key(p.name))
        for pdf in files:
            if pdf.exists() and pdf.suffix.lower() == ".pdf":
                merger.append(str(pdf))
        merger.write(str(dst))
    finally:
        merger.close()
    return dst

