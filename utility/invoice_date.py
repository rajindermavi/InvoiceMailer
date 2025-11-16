import re

from pathlib import Path
from typing import Optional, Tuple, List
from dateutil import parser as dateparser

import configparser
import fitz  # PyMuPDF

from config import (
    load_env_if_present,
    load_config,
    get_invoice_folder,
    get_soa_folder,
    get_client_directory,
    get_date_pattern,
)
load_env_if_present()
cfg = load_config()

try:
    import pytesseract
    from PIL import Image
    OCR_LIB_AVAILABLE = True
except Exception:
    OCR_LIB_AVAILABLE = False

# ---- DATE BOX ----
USE_PERCENT = cfg.getboolean("date_box", "use_percent", fallback=True)

x0_pct = cfg.getfloat("date_box", "x0", fallback=0.01)
y0_pct = cfg.getfloat("date_box", "y0", fallback=0.3275)
x1_pct = cfg.getfloat("date_box", "x1", fallback=0.12)
y1_pct = cfg.getfloat("date_box", "y1", fallback=0.34)
DATE_BOX_PCT: Optional[Tuple[float, float, float, float]] = (x0_pct, y0_pct, x1_pct, y1_pct)

x0_pts = cfg.getfloat("date_box", "x0_points", fallback=0.0)
y0_pts = cfg.getfloat("date_box", "y0_points", fallback=0.0)
x1_pts = cfg.getfloat("date_box", "x1_points", fallback=0.0)
y1_pts = cfg.getfloat("date_box", "y1_points", fallback=0.0)
DATE_BOX_POINTS: Optional[Tuple[float, float, float, float]] = (x0_pts, y0_pts, x1_pts, y1_pts)

# ---- PROCESSING ----
PAGE_INDEX = cfg.getint("processing", "page_index", fallback=0)
TRY_OCR_IF_NEEDED = cfg.getboolean("processing", "try_ocr_if_needed", fallback=True)

# ---- REGEX ----

DATE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p.pattern, p.flags | re.IGNORECASE)
    for p in get_date_pattern(cfg)
]

# ------------- HELPERS ------------- #

def percent_rect_to_points(page: fitz.Page, pct_box: Tuple[float, float, float, float]) -> fitz.Rect:
    width, height = page.rect.width, page.rect.height
    x0 = pct_box[0] * width
    y0 = pct_box[1] * height
    x1 = pct_box[2] * width
    y1 = pct_box[3] * height
    return fitz.Rect(x0, y0, x1, y1)


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
    finally:
        img.close()


# ------------- CORE EXTRACTION ------------- #

def extract_invoice_date(
    pdf_path: Path,
    page_index: int = PAGE_INDEX,
    use_percent: bool = USE_PERCENT,
    percentage_box: Optional[Tuple[float, float, float, float]] = DATE_BOX_PCT,
    points_box: Optional[Tuple[float, float, float, float]] = DATE_BOX_POINTS,
) -> Optional[str]:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]

        if use_percent:
            if not percentage_box:
                raise ValueError("percentage_box is None but use_percent=True")
            rect = percent_rect_to_points(page, percentage_box)
        else:
            if not points_box:
                raise ValueError("points_box is None but use_percent=False")
            rect = fitz.Rect(*points_box)

        # 1) Direct text extraction in region
        region_text = extract_text_from_region(page, rect)
        candidates = find_date_strings(region_text)
        iso = normalize_first_date(candidates)
        if iso:
            return iso

        # 2) Slightly expanded region (to catch line breaks)
        padding = 10
        rect_expanded = fitz.Rect(
            rect.x0 - padding,
            rect.y0 - padding,
            rect.x1 + padding,
            rect.y1 + padding,
        )
        region_text2 = extract_text_from_region(page, rect_expanded)
        candidates2 = find_date_strings(region_text2)
        iso2 = normalize_first_date(candidates2)
        if iso2:
            return iso2

        # 3) OCR fallback
        ocr_txt = ocr_text_from_region(page, rect_expanded)
        candidates3 = find_date_strings(ocr_txt)
        return normalize_first_date(candidates3)

    finally:
        doc.close()
