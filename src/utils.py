"""
utils.py
--------
Shared utility helpers used across the pipeline.

Responsibilities:
  - Build and validate all required output directory paths for a run.
  - Derive lecture_name from an input PDF file path.
  - Provide any other small, reusable helper functions.
"""

import os


def derive_lecture_name(pdf_path: str) -> str:
    """
    Extract the lecture name from the input PDF file path.

    The lecture name is the PDF filename without its extension.

    Args:
        pdf_path: Absolute or relative path to the input PDF.

    Returns:
        Lecture name string (e.g., "Lecture_03_Memory").
    """
    basename = os.path.basename(pdf_path)          # "Lecture_03_Memory.pdf"
    lecture_name, _ = os.path.splitext(basename)    # "Lecture_03_Memory"
    return lecture_name


def build_output_paths(base_output_dir: str, module_name: str, lecture_name: str) -> dict:
    """
    Construct all required output directory / file paths for a run.

    Expected structure under base_output_dir:
        {module_name}/
            images/{lecture_name}/pictures/
            OCR/
            Obsidian/
            PDF/
            Anki/
            dict/

    Args:
        base_output_dir: Root output directory (e.g., "output/").
        module_name:     Name of the module / course.
        lecture_name:    Derived lecture name.

    Returns:
        Dict mapping logical path keys to absolute path strings, e.g.:
            {
                "images_dir":     "…/images/{lecture_name}/pictures/",
                "ocr_file":       "…/OCR/{lecture_name}_raw.json",
                "obsidian_file":  "…/Obsidian/obs_{lecture_name}.md",
                "pdf_file":       "…/PDF/result_{lecture_name}.pdf",
                "anki_file":      "…/Anki/APKG_{lecture_name}.apkg",
                "dict_file":      "…/dict/{lecture_name}.json",
            }
    """
    module_root = os.path.join(base_output_dir, module_name)

    return {
        "images_dir":    os.path.join(module_root, "images", lecture_name, "pictures"),
        "ocr_file":      os.path.join(module_root, "OCR", f"{lecture_name}_raw.json"),
        "obsidian_file": os.path.join(module_root, "Obsidian", f"obs_{lecture_name}.md"),
        "pdf_file":      os.path.join(module_root, "PDF", f"result_{lecture_name}.pdf"),
        "anki_file":     os.path.join(module_root, "Anki", f"APKG_{lecture_name}.apkg"),
        "dict_file":     os.path.join(module_root, "dict", f"{lecture_name}.json"),
    }


def ensure_dirs(paths: dict) -> None:
    """
    Create all directories referenced in *paths* (if they don't exist).

    For keys ending in ``_dir`` the value is treated as a directory path.
    For all other keys (files) the parent directory is created.

    Args:
        paths: Dict returned by build_output_paths().
    """
    for key, path in paths.items():
        if key.endswith("_dir"):
            os.makedirs(path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)

