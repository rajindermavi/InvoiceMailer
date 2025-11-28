import re

from pathlib import Path
from typing import List, Optional, Tuple

from dateutil import parser as dateparser
import fitz  # PyMuPDF

from config import (
    get_date_pattern,
    load_config,
    load_env_if_present,
)

load_env_if_present()
cfg = load_config()

try:
    import pytesseract
    from PIL import Image

    OCR_LIB_AVAILABLE = True
except Exception:
    OCR_LIB_AVAILABLE = False

PdfBox = Tuple[float, float, float, float]
DEFAULT_BOXES_PCT: dict[str, PdfBox] = {
    "inv_date":     (0.01, 0.3275, 0.12, 0.34),
    "soa_date":     (0.72, 0.0775, 0.815, 0.092),
    "soa_office":   (0.85, 0.0775, 0.92, 0.092),
}
DEFAULT_BOXES_POINTS: dict[str, PdfBox] = {}

# ---- PROCESSING ----
DEFAULT_USE_PERCENT = cfg.getboolean("pdf_rect", "use_percent", fallback=True)
PAGE_INDEX = cfg.getint("processing", "page_index", fallback=0)
TRY_OCR_IF_NEEDED = cfg.getboolean("processing", "try_ocr_if_needed", fallback=True)

# ---- REGEX ----
DATE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p.pattern, p.flags | re.IGNORECASE) for p in get_date_pattern(cfg)
]

# ------------- HELPERS ------------- #

def percent_rect_to_points(page: fitz.Page, pct_box: PdfBox) -> fitz.Rect:
    """
        convert percent box to point box
    """
    width, height = page.rect.width, page.rect.height
    x0 = pct_box[0] * width
    y0 = pct_box[1] * height
    x1 = pct_box[2] * width
    y1 = pct_box[3] * height
    return fitz.Rect(x0, y0, x1, y1)

def _read_box_from_config(field: str, use_percent: bool) -> Optional[PdfBox]:
    """
        fetch box dimensions from config file
    """
    suffix = "_pct" if use_percent else ""
    key_prefix = f"{field}_"
    coords: List[float] = []
    for coord in ("x0", "y0", "x1", "y1"):
        option = f"{key_prefix}{coord}{suffix}"
        if not cfg.has_option("pdf_rect", option):
            return None
        coords.append(cfg.getfloat("pdf_rect", option))
    return tuple(coords)  # type: ignore[return-value]

def _resolve_box(
    field: str,
    use_percent: Optional[bool] = None,
    percentage_box: Optional[PdfBox] = None,
    points_box: Optional[PdfBox] = None,
) -> tuple[PdfBox, bool]:
    """
    Resolve the box for a given field from overrides or config.

    Preference: explicit args -> config -> defaults. Raises if nothing is found.
    """
    use_pct = DEFAULT_USE_PERCENT if use_percent is None else use_percent

    if use_pct:
        if percentage_box is not None:
            return percentage_box, True
        if (cfg_box := _read_box_from_config(field, use_percent=True)) is not None:
            return cfg_box, True
        if field in DEFAULT_BOXES_PCT:
            return DEFAULT_BOXES_PCT[field], True
    else:
        if points_box is not None:
            return points_box, False
        if (cfg_box := _read_box_from_config(field, use_percent=False)) is not None:
            return cfg_box, False
        if field in DEFAULT_BOXES_POINTS:
            return DEFAULT_BOXES_POINTS[field], False

    raise ValueError(
        f"No coordinates found for '{field}' "
        f"(use_percent={use_pct}). Configure in [pdf_rect]."
    )

def extract_text_from_region(page: fitz.Page, rect: fitz.Rect) -> str:
    return page.get_text("text", clip=rect)

def ocr_text_from_region(page: fitz.Page, rect: fitz.Rect, scale: float = 2.0) -> str:
    if not (TRY_OCR_IF_NEEDED and OCR_LIB_AVAILABLE):
        return ""
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    try:
        return pytesseract.image_to_string(img)
    except (pytesseract.TesseractNotFoundError, OSError):
        # Tesseract binary not installed or not on PATH; fallback to empty text
        return ""
    finally:
        img.close()

def _dedupe_preserve_order(texts: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for txt in texts:
        if txt not in seen:
            seen.add(txt)
            result.append(txt)
    return result

#-------- Extract Text ------

def extract_pdf_text(
    pdf_path: Path,
    field: str,
    *,
    page_index: int = PAGE_INDEX,
    use_percent: Optional[bool] = None,
    percentage_box: Optional[PdfBox] = None,
    points_box: Optional[PdfBox] = None,
    padding: float = 10.0,
) -> str:
    """
    Extract text from a configured rectangle, optionally expanding and OCR'ing it.
    The combined text (direct, expanded, OCR) is returned as a newline-joined string.
    """
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        box, use_pct = _resolve_box(
            field, use_percent=use_percent, percentage_box=percentage_box, points_box=points_box
        )
        rect = percent_rect_to_points(page, box) if use_pct else fitz.Rect(*box)

        texts: List[str] = []

        direct = extract_text_from_region(page, rect).strip()
        if direct:
            texts.append(direct)

        rect_expanded = fitz.Rect(
            rect.x0 - padding,
            rect.y0 - padding,
            rect.x1 + padding,
            rect.y1 + padding,
        )

        expanded = extract_text_from_region(page, rect_expanded).strip()
        if expanded:
            texts.append(expanded)

        ocr_txt = ocr_text_from_region(page, rect_expanded).strip()
        if ocr_txt:
            texts.append(ocr_txt)

        combined = "\n".join(_dedupe_preserve_order([t for t in texts if t]))
        return combined
    finally:
        doc.close()

# -------------  EXTRACT DATE ------------- #

def find_date_strings(text: str) -> List[str]:
    matches: List[str] = []
    if not text:
        return matches
    for pattern in DATE_PATTERNS:
        matches.extend(m.group(0) for m in pattern.finditer(text))
    return matches

def normalize_first_date(dates: List[str]) -> Optional[str]:
    for d in dates:
        try:
            # Adjust dayfirst depending on your format
            dt = dateparser.parse(d, dayfirst=False, fuzzy=True)
            return dt.date().isoformat()
        except Exception:
            continue
    return None

def extract_pdf_date(
    pdf_path: Path,
    field: str,
    *,
    page_index: int = PAGE_INDEX,
    use_percent: Optional[bool] = None,
    percentage_box: Optional[PdfBox] = None,
    points_box: Optional[PdfBox] = None,
    padding: float = 10.0,
) -> Optional[str]:
    """
    Extract a date string from the configured rectangle and normalize it to ISO.

    The default field uses the invoice date rectangle (inv_date); pass a different
    field name to reuse the same logic for other PDF regions.
    """
    combined_text = extract_pdf_text(
        pdf_path,
        field,
        page_index=page_index,
        use_percent=use_percent,
        percentage_box=percentage_box,
        points_box=points_box,
        padding=padding,
    )

    candidates = find_date_strings(combined_text)
    return normalize_first_date(candidates)
