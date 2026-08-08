"""
pdf_handler.py
--------------
Step A & B of the pipeline.

Responsibilities:
  - Convert input PDF pages to PNG images (Step A)
  - Detect relevance of each slide by analysing the left-edge colour
    using OpenCV (yellow highlight detection) (Step A)
  - Build and persist the page-metadata dictionary to
    output/{Module}/dict/{lecture_name}.json (Step A)
  - Reconstruct a compressed PDF containing only relevant pages
    via PyMuPDF (fitz), with DPI fallback logic (Step B)
"""

import json
import os
import shutil
import subprocess

import cv2
import pymupdf as fitz  # PyMuPDF (replaces deprecated `import fitz`)
import numpy as np

# ── Tunables ────────────────────────────────────────────────────────
IMAGE_DPI = 200               # DPI used when rendering PDF pages to PNG
LEFT_EDGE_RATIO = 0.07       # Fraction of image width treated as "left edge"
YELLOW_PIXEL_THRESHOLD = 0.1  # Min ratio of yellow pixels in the strip to flag relevance

# HSV range that covers typical yellow highlighter colours.
# H: 20-35 (yellow hues), S: 80-255 (saturated), V: 80-255 (bright)
YELLOW_HSV_LOWER = np.array([20, 80, 80])
YELLOW_HSV_UPPER = np.array([35, 255, 255])


def pdf_to_images(pdf_path: str, output_dir: str) -> list[str]:
    """
    Convert every page of the PDF at *pdf_path* to a PNG image.

    Images are saved as pic1.png, pic2.png, … (1-indexed) inside
    *output_dir*.

    Args:
        pdf_path:   Absolute path to the source PDF.
        output_dir: Directory where images will be saved
                    (images/{lecture_name}/pictures/).

    Returns:
        Ordered list of absolute paths to the generated image files.
    """
    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    image_paths: list[str] = []

    zoom = IMAGE_DPI / 72  # fitz default is 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=matrix)
        filename = f"pic{page_num + 1}.png"
        out_path = os.path.join(output_dir, filename)
        pix.save(out_path)
        image_paths.append(out_path)

    doc.close()
    print(f"[pdf_to_images] Converted {len(image_paths)} pages → {output_dir}")
    return image_paths


def detect_relevance(image_path: str) -> bool:
    """
    Analyse the left edge of *image_path* for yellow highlights.

    The leftmost 15 % of the image is converted to HSV and a yellow
    colour mask is applied.  If the fraction of yellow pixels in that
    strip exceeds YELLOW_PIXEL_THRESHOLD the slide is considered
    relevant.

    Args:
        image_path: Absolute path to a slide image.

    Returns:
        True if yellow is detected on the left edge, False otherwise.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"[detect_relevance] WARNING: could not read {image_path}")
        return False

    height, width = img.shape[:2]
    left_strip_width = int(width * LEFT_EDGE_RATIO)
    left_strip = img[:, :left_strip_width]

    hsv = cv2.cvtColor(left_strip, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, YELLOW_HSV_LOWER, YELLOW_HSV_UPPER)

    yellow_pixels = cv2.countNonZero(mask)
    total_pixels = left_strip_width * height
    ratio = yellow_pixels / total_pixels

    return ratio >= YELLOW_PIXEL_THRESHOLD


def build_page_dict(image_paths: list[str]) -> dict:
    """
    Build the page-metadata dictionary for all slides.

    Schema per entry:
        {page_number: {"is_relevant": bool, "question": "", "answer": ""}}

    Also prints a summary of irrelevant pages to the console (without
    opening a GUI window).

    Args:
        image_paths: Ordered list of image paths (index = page number).

    Returns:
        Populated page-metadata dictionary.
    """
    page_dict: dict[int, dict] = {}

    for idx, img_path in enumerate(image_paths):
        page_number = idx + 1  # 1-indexed
        relevant = detect_relevance(img_path)
        page_dict[page_number] = {
            "is_relevant": relevant,
            "question": "",
            "answer": "",
        }

    # ── Console summary of irrelevant pages ──
    irrelevant_pages = [p for p, v in page_dict.items() if not v["is_relevant"]]
    relevant_count = len(page_dict) - len(irrelevant_pages)

    print(f"\n[build_page_dict] {relevant_count}/{len(page_dict)} pages marked relevant.")
    if irrelevant_pages:
        print(f"[build_page_dict] Irrelevant pages: {irrelevant_pages}")
    else:
        print("[build_page_dict] All pages are relevant.")

    return page_dict


def save_page_dict(page_dict: dict, output_path: str) -> None:
    """
    Persist *page_dict* as JSON to *output_path*.

    Args:
        page_dict:   The page-metadata dictionary.
        output_path: Destination file path (…/dict/{lecture_name}.json).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # JSON keys must be strings; convert int page numbers.
    serialisable = {str(k): v for k, v in page_dict.items()}

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(serialisable, fh, indent=2, ensure_ascii=False)

    print(f"[save_page_dict] Dictionary saved → {output_path}")


def _scale_pdf_with_gs(input_path: str, output_path: str, dpi: int) -> str:
    """
    Skaliert PDF mit Ghostscript (verkleinert Bilder innerhalb der PDF).
    """
    print(f"[Ghostscript] 📉 Skaliere PDF auf {dpi} DPI...")
    # Pfad anpassen, falls Ghostscript woanders installiert ist
    GHOSTSCRIPT_PATH = r"C:\Program Files\gs\gs10.07.1\bin\gswin64c.exe"
    
    cmd = [
        GHOSTSCRIPT_PATH,
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=/screen", 
        "-dDownsampleColorImages=true",
        f"-dColorImageResolution={dpi}",
        "-dDownsampleGrayImages=true",
        f"-dGrayImageResolution={dpi}",
        "-dDownsampleMonoImages=true",
        f"-dMonoImageResolution={dpi}",
        f"-sOutputFile={output_path}",
        input_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        size_kb = os.path.getsize(output_path) / 1024
        print(f"[Ghostscript] ✅ Skaliert: {output_path} ({size_kb:.1f} KB)")
        return output_path
    except Exception as e:
        print(f"[Ghostscript] ⚠️ Ghostscript fehlgeschlagen: {e}")
        shutil.copy(input_path, output_path)
        return output_path


def build_relevant_pdf(
    source_pdf_path: str,
    page_dict: dict,
    output_path: str,
) -> None:
    """
    Create a new PDF containing only the pages marked as relevant.

    Compression logic:
      1. Native Vector Extraction
      2. If > 5 MB, scale with Ghostscript at 100 DPI
      3. If still > 5 MB, scale with Ghostscript at 70 DPI.

    Args:
        source_pdf_path: Path to the original input PDF.
        page_dict:       Page-metadata dictionary (used to filter pages).
        output_path:     Destination path for the result PDF.
    """
    MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

    # Determine which pages are relevant (page_dict keys may be int or str).
    relevant_pages: list[int] = []
    for key, meta in page_dict.items():
        if meta.get("is_relevant"):
            relevant_pages.append(int(key) - 1)  # fitz uses 0-indexed pages
    relevant_pages.sort()

    if not relevant_pages:
        print("[build_relevant_pdf] No relevant pages found – skipping PDF creation.")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ── Try 1: Native Vector Extraction (Lossless) ──
    out_doc = fitz.open(source_pdf_path)
    out_doc.select(relevant_pages)
    out_doc.save(output_path, garbage=4, deflate=True)
    out_doc.close()
    
    size = os.path.getsize(output_path)
    print(f"[build_relevant_pdf] Native extraction → {size / 1024 / 1024:.2f} MB")

    if size > MAX_SIZE_BYTES:
        # ── Try 2: Ghostscript Compression ──
        print("[build_relevant_pdf] Size > 5MB. Running Ghostscript compression...")
        tmp_output = output_path + ".tmp.pdf"
        
        # 100 DPI
        _scale_pdf_with_gs(output_path, tmp_output, 100)
        size = os.path.getsize(tmp_output)
        
        if size > MAX_SIZE_BYTES:
            print("[build_relevant_pdf] Still > 5MB. Retrying at 70 DPI...")
            # 70 DPI
            _scale_pdf_with_gs(output_path, tmp_output, 70)
            size = os.path.getsize(tmp_output)

        shutil.move(tmp_output, output_path)

        if size > MAX_SIZE_BYTES:
            print("[build_relevant_pdf] WARNING: File still exceeds 5 MB. Saving as-is.")

    print(f"[build_relevant_pdf] Saved → {output_path}")

