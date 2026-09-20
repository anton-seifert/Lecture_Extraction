"""
ocr_processor.py
----------------
Step C of the pipeline.

Responsibilities:
  - Run pytesseract OCR on the relevant slide images.
  - Apply stop-word / stop-phrase filtering (case-insensitive).
  - Format and save raw OCR output to
    output/{Module}/OCR/{lecture_name}_raw.json
"""

import json
import os
import re

import pytesseract
from PIL import Image

# Stop words / phrases to strip from OCR output (case-insensitive).
STOP_WORDS: list[str] = [
    "chapters",
    "slides",
    "page",
    "KIT",
    "Karlsruhe Institute of Technology",
    "Karlsruhe Institut of Technology",
    "Karlsruher Institut für Technologie",
    "seite",
]

# Tesseract language string – German + English.
TESSERACT_LANG = "deu+eng"


def run_ocr(image_path: str) -> str:
    """
    Run pytesseract OCR on the image at *image_path*.

    Args:
        image_path: Absolute path to the slide image.

    Returns:
        Raw extracted text string.
    """
    img = Image.open(image_path)
    text: str = pytesseract.image_to_string(img, lang=TESSERACT_LANG)
    return text


def filter_stop_words(text: str) -> str:
    """
    Remove all STOP_WORDS entries from *text* (case-insensitive).

    Longer phrases are processed first so that multi-word entries
    (e.g. "Karlsruhe Institute of Technology") are removed before
    their sub-strings (e.g. "KIT") are checked.

    After removal any resulting runs of multiple spaces or blank lines
    are collapsed.

    Args:
        text: Raw OCR text.

    Returns:
        Filtered text with stop words removed.
    """
    # Sort longest-first so multi-word phrases are matched before
    # their individual words.
    sorted_words = sorted(STOP_WORDS, key=len, reverse=True)

    for word in sorted_words:
        # \b word-boundary anchors prevent partial-word matches
        # (e.g. "page" won't strip "pages" or "homepage").
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        text = pattern.sub("", text)

    # Collapse leftover whitespace artefacts.
    text = re.sub(r" {2,}", " ", text)        # multiple spaces → one
    text = re.sub(r"\n{3,}", "\n\n", text)    # 3+ newlines → 2
    text = text.strip()
    return text


def process_relevant_slides(
    image_paths: list[str],
    page_dict: dict,
    output_path: str,
) -> None:
    """
    OCR all relevant slides, filter stop words, and write the results
    to a JSON file.

    Output format:
        [
            {"slide": 1, "text": "<extracted_text>"},
            {"slide": 3, "text": "<extracted_text>"}
        ]

    Args:
        image_paths: Ordered list of all slide image paths.
        page_dict:   Page-metadata dictionary (used to identify
                     relevant pages).
        output_path: Destination path for the JSON OCR file
                     (…/OCR/{lecture_name}_raw.json).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    data: list[dict] = []

    for idx, img_path in enumerate(image_paths):
        page_number = idx + 1  # 1-indexed
        key = str(page_number)

        # page_dict keys may be int or str depending on whether it was
        # loaded from JSON (str) or built in-memory (int).
        meta = page_dict.get(key) or page_dict.get(page_number)
        if meta is None or not meta.get("is_relevant"):
            continue

        raw_text = run_ocr(img_path)
        filtered_text = filter_stop_words(raw_text)

        # Flatten to a single line per slide (replace newlines with spaces).
        one_line = " ".join(filtered_text.split())
        data.append({"slide": page_number, "text": one_line})

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    print(f"[process_relevant_slides] OCR complete – {len(data)} slides → {output_path}")

