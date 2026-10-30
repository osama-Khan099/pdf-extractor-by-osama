"""PDF text extraction that runs fully offline.

Text-based pages are read directly with PyMuPDF. Pages with no text layer
(scans, photos) fall back to OCR with RapidOCR, which ships its models inside
the pip package so no internet connection or separate install is needed.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Optional

import pymupdf as fitz

OCR_AUTO = "auto"      # OCR only pages without a usable text layer
OCR_ALWAYS = "always"  # OCR every page
OCR_OFF = "off"        # never OCR

# A page with fewer real characters than this is treated as scanned.
MIN_TEXT_CHARS = 25
# ...but only if images cover at least this share of it (skips blank pages).
MIN_IMAGE_COVER = 0.10
# 200 DPI reads normal print about as well as 300 DPI in half the time.
OCR_DPI = 200
OCR_MAX_SIDE = 3000  # pixels; keeps oversized pages (A3, posters) quick


@dataclass
class Paragraph:
    text: str
    size: float = 0.0
    bold: bool = False
    heading: int = 0  # 0 = body, 1..3 = heading level


@dataclass
class Page:
    number: int
    paragraphs: list[Paragraph] = field(default_factory=list)
    ocr: bool = False


@dataclass
class Document:
    pages: list[Page]

    def to_text(self) -> str:
        pages = ("\n\n".join(p.text for p in pg.paragraphs) for pg in self.pages)
        return "\n\n".join(t for t in pages if t)

    @property
    def ocr_pages(self) -> list[int]:
        return [p.number for p in self.pages if p.ocr]


class ExtractionError(Exception):
    pass


_ocr_engine = None


def ocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def _get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        # The angle classifier only helps with upside-down lines and roughly
        # doubles the time per page, so it stays off. RapidOCR 1.2 calls the
        # option use_angle_cls and 1.3+ calls it use_cls; each ignores the other.
        _ocr_engine = RapidOCR(use_angle_cls=False, use_cls=False)
    return _ocr_engine


def parse_page_range(spec: str, page_count: int) -> list[int]:
    """Turn "1-5, 8, 10-" into 0-based page indices. Empty means all pages."""
    spec = spec.strip().lower()
    if not spec or spec == "all":
        return list(range(page_count))
    pages: list[int] = []
    for part in spec.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                start = int(a) if a.strip() else 1
                end = int(b) if b.strip() else page_count
            else:
                start = end = int(part)
        except ValueError:
            raise ValueError(f"Invalid page range: {part}") from None
        if start < 1 or end < start:
            raise ValueError(f"Invalid page range: {part}")
        pages.extend(range(start - 1, min(end, page_count)))
    pages = sorted(set(pages))
    if not pages:
        raise ValueError(f"No pages in range (this PDF has {page_count}).")
    return pages


def _clean(s: str) -> str:
    return " ".join(s.replace("\u00ad", "").split())


def _text_page(page: fitz.Page) -> list[Paragraph]:
    data = page.get_text("dict", sort=True)
    paras: list[Paragraph] = []
    for block in data["blocks"]:
        if block.get("type") != 0:
            continue
        lines, sizes, bold_chars, chars = [], [], 0, 0
        for line in block["lines"]:
            spans = line["spans"]
            line_text = "".join(s["text"] for s in spans)
            if not line_text.strip():
                continue
            lines.append(line_text.strip())
            for s in spans:
                n = len(s["text"].strip())
                chars += n
                sizes.extend([s["size"]] * max(n, 1))
                if s["flags"] & 16 or "bold" in s["font"].lower():
                    bold_chars += n
        if not lines:
            continue
        # Rejoin hyphenated line breaks, otherwise join lines with spaces.
        text = lines[0]
        for nxt in lines[1:]:
            if text.endswith("-") and nxt[:1].islower():
                text = text[:-1] + nxt
            else:
                text += " " + nxt
        paras.append(Paragraph(
            text=_clean(text),
            size=statistics.median(sizes) if sizes else 0.0,
            bold=chars > 0 and bold_chars / chars > 0.6,
        ))
    return paras


def _looks_scanned(page: fitz.Page) -> bool:
    area = abs(page.rect) or 1
    covered = sum(abs(fitz.Rect(img["bbox"]) & page.rect) for img in page.get_image_info())
    return covered / area >= MIN_IMAGE_COVER


def _page_image(page: fitz.Page):
    import numpy as np
    zoom = OCR_DPI / 72
    longest = max(page.rect.width, page.rect.height) * zoom
    if longest > OCR_MAX_SIDE:
        zoom *= OCR_MAX_SIDE / longest
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return img[:, :, ::-1].copy()  # RGB -> BGR, as OpenCV expects


def _ocr_page(page: fitz.Page) -> list[Paragraph]:
    engine = _get_ocr()
    result, _ = engine(_page_image(page))
    if not result:
        return []
    # result: [[box, text, score], ...]; box = 4 corner points.
    items = []
    for box, text, _score in result:
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        items.append((min(ys), max(ys), min(xs), text))
    items.sort(key=lambda t: (t[0], t[2]))

    # Group boxes into lines, then lines into paragraphs by vertical gaps.
    lines: list[list] = []
    for top, bottom, left, text in items:
        if lines and abs(top - lines[-1][0]) < (bottom - top) * 0.5:
            lines[-1][3].append((left, text))
            lines[-1][1] = max(lines[-1][1], bottom)
        else:
            lines.append([top, bottom, left, [(left, text)]])
    heights = [ln[1] - ln[0] for ln in lines] or [1]
    typical = statistics.median(heights)

    paras: list[Paragraph] = []
    current: list[str] = []
    prev_bottom = None
    for top, bottom, _left, parts in lines:
        text = " ".join(t for _, t in sorted(parts))
        if prev_bottom is not None and top - prev_bottom > typical * 0.8 and current:
            paras.append(Paragraph(_clean(" ".join(current))))
            current = []
        current.append(text)
        prev_bottom = bottom
    if current:
        paras.append(Paragraph(_clean(" ".join(current))))
    return paras


def _mark_headings(doc: Document) -> None:
    sizes = [p.size for pg in doc.pages for p in pg.paragraphs if p.size]
    if not sizes:
        return
    body = statistics.median(sizes)
    for pg in doc.pages:
        for p in pg.paragraphs:
            if not p.size or len(p.text) > 200:
                continue
            ratio = p.size / body
            if ratio >= 1.6:
                p.heading = 1
            elif ratio >= 1.3:
                p.heading = 2
            elif ratio >= 1.12 or (p.bold and len(p.text) < 100 and not p.text.endswith(".")):
                p.heading = 3


def build_document(pages: list[Page]) -> Document:
    doc = Document(pages)
    _mark_headings(doc)
    return doc


def extract(
    path: str,
    ocr_mode: str = OCR_AUTO,
    password: Optional[str] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    pages: Optional[str] = None,
    on_page: Optional[Callable[[Page], None]] = None,
) -> Document:
    """Extract text from the PDF at *path*.

    *pages* is a range like "1-20, 25" (default: all pages).
    progress(done, total, message) is called before slow steps and after
    each page; on_page(page) gets each page as soon as it is ready.
    """
    try:
        pdf = fitz.open(path)
    except Exception as e:
        raise ExtractionError(f"Could not open PDF: {e}") from e

    with pdf:
        if pdf.needs_pass:
            if not password or not pdf.authenticate(password):
                raise ExtractionError("This PDF is password protected.")
        try:
            wanted = parse_page_range(pages or "", pdf.page_count)
        except ValueError as e:
            raise ExtractionError(str(e)) from e
        use_ocr = ocr_mode != OCR_OFF and ocr_available()
        total = len(wanted)
        done_pages: list[Page] = []
        for done, i in enumerate(wanted):
            if cancelled and cancelled():
                raise ExtractionError("Cancelled.")
            page = pdf[i]
            paras: list[Paragraph] = []
            did_ocr = False
            if ocr_mode != OCR_ALWAYS:
                paras = _text_page(page)
            chars = sum(len(p.text.strip()) for p in paras)
            if use_ocr and (ocr_mode == OCR_ALWAYS
                            or (chars < MIN_TEXT_CHARS and _looks_scanned(page))):
                if progress:
                    progress(done, total, f"Reading scanned page {i + 1} (OCR)...")
                ocr_paras = _ocr_page(page)
                if sum(len(p.text) for p in ocr_paras) > chars:
                    paras, did_ocr = ocr_paras, True
            result = Page(number=i + 1, paragraphs=paras, ocr=did_ocr)
            done_pages.append(result)
            if on_page:
                on_page(result)
            if progress:
                progress(done + 1, total, f"Page {i + 1}")

    return build_document(done_pages)


def save_txt(text: str, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip() + "\n")


def save_docx(doc: Optional[Document], path: str, text: Optional[str] = None) -> None:
    """Write a DOCX. Uses the structured *doc* (keeps headings and page
    breaks) unless *text* is given, e.g. after the user edited the preview."""
    from docx import Document as Docx
    from docx.enum.text import WD_BREAK

    out = Docx()
    if text is not None:
        for chunk in text.replace("\r\n", "\n").split("\n\n"):
            chunk = chunk.strip("\n")
            if chunk:
                out.add_paragraph(chunk)
    else:
        for idx, page in enumerate(doc.pages):
            for p in page.paragraphs:
                if p.heading:
                    out.add_heading(p.text, level=p.heading)
                else:
                    para = out.add_paragraph(p.text)
                    if p.bold:
                        for run in para.runs:
                            run.bold = True
            if idx < len(doc.pages) - 1 and page.paragraphs:
                out.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    out.save(path)
