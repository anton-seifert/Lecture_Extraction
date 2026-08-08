"""
main.py
-------
Entry point for the Lecture Extraction pipeline.

Provides six CLI sub-commands that compose the pipeline steps:

  full               – A → B → C → D → E  (everything)
  obsidian-scratch   – A → B → C → D      (images, PDF, OCR, Obsidian notes)
  obsidian-existing  – D only              (Obsidian notes from an existing OCR file)
  anki-full          – A → C → E           (images, OCR-for-dict, Anki Q&A + .apkg)
  anki-qa            – E (generate Q&A)    (images & dict exist, run LLM + pack .apkg)
  anki-pack          – E (pack only)       (dict with Q&A exists, just build .apkg)
  pdf-only           – A → B               (images, relevance detection, filtered PDF)

Usage examples:
  python src/main.py full       --pdf "lecture.pdf" --module "SWT1"
  python src/main.py full       --folder "./SWT1/"  # module derived from folder name → "SWT1"
  python src/main.py full       --folder "./SWT1/" --module "Softwaretechnik 1"  # explicit override
  python src/main.py obsidian-existing --module "SWT1" --lecture "Lecture_03"
  python src/main.py anki-pack  --module "SWT1" --lecture "Lecture_03"
  python src/main.py pdf-only --pdf "Originals\robotics II\Lecture01.pdf" --module "robotics_II"

"""

import argparse
import json
import os
import sys

from anki_export import build_anki_package, generate_qa_for_slides
from llm_client import generate_obsidian_notes, get_gemini_client
from ocr_processor import process_relevant_slides
from pdf_handler import build_page_dict, build_relevant_pdf, pdf_to_images, save_page_dict
from utils import build_output_paths, derive_lecture_name, ensure_dirs

# ── Default output base directory (relative to project root) ────────
BASE_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")


# =====================================================================
# Helper: load an existing page-metadata JSON
# =====================================================================

def _load_page_dict(dict_path: str) -> dict:
    """Load and return the page-metadata dictionary from *dict_path*."""
    with open(dict_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _collect_image_paths(images_dir: str) -> list[str]:
    """Return an ordered list of image paths (pic1.png, pic2.png, …)."""
    files = sorted(
        [f for f in os.listdir(images_dir) if f.startswith("pic") and f.endswith(".png")],
        key=lambda f: int(f.replace("pic", "").replace(".png", "")),
    )
    return [os.path.join(images_dir, f) for f in files]


# =====================================================================
# Workflow 1 – full  (A → B → C → D → E)
# =====================================================================

def workflow_full(pdf_path: str, module_name: str) -> None:
    """Run the complete pipeline: images → PDF → OCR → Obsidian → Anki."""
    lecture_name = derive_lecture_name(pdf_path)
    paths = build_output_paths(BASE_OUTPUT_DIR, module_name, lecture_name)
    ensure_dirs(paths)

    # Step A
    image_paths = pdf_to_images(pdf_path, paths["images_dir"])
    page_dict = build_page_dict(image_paths)
    save_page_dict(page_dict, paths["dict_file"])

    # Step B
    build_relevant_pdf(pdf_path, page_dict, paths["pdf_file"])

    # Step C
    process_relevant_slides(image_paths, page_dict, paths["ocr_file"])

    # Step D
    client = get_gemini_client()
    generate_obsidian_notes(paths["ocr_file"], paths["obsidian_file"], lecture_name, client=client)

    # Step E
    page_dict = generate_qa_for_slides(image_paths, page_dict, paths["dict_file"], client=client)
    deck_name = f"{module_name} – {lecture_name}"
    build_anki_package(page_dict, image_paths, deck_name, paths["anki_file"])

    print("\n✅ Full pipeline complete.")


# =====================================================================
# Workflow 2 – obsidian-scratch  (A → B → C → D)
# =====================================================================

def workflow_obsidian_scratch(pdf_path: str, module_name: str) -> None:
    """Build Obsidian notes from a PDF: images → PDF → OCR → Gemini."""
    lecture_name = derive_lecture_name(pdf_path)
    paths = build_output_paths(BASE_OUTPUT_DIR, module_name, lecture_name)
    ensure_dirs(paths)

    # Step A
    image_paths = pdf_to_images(pdf_path, paths["images_dir"])
    page_dict = build_page_dict(image_paths)
    save_page_dict(page_dict, paths["dict_file"])

    # Step B
    build_relevant_pdf(pdf_path, page_dict, paths["pdf_file"])

    # Step C
    process_relevant_slides(image_paths, page_dict, paths["ocr_file"])

    # Step D
    generate_obsidian_notes(paths["ocr_file"], paths["obsidian_file"], lecture_name)

    print("\n✅ Obsidian (from scratch) pipeline complete.")


# =====================================================================
# Workflow 3 – obsidian-existing  (D only)
# =====================================================================

def workflow_obsidian_existing(module_name: str, lecture_name: str) -> None:
    """Generate Obsidian notes from an already-existing raw OCR file."""
    paths = build_output_paths(BASE_OUTPUT_DIR, module_name, lecture_name)

    if not os.path.isfile(paths["ocr_file"]):
        sys.exit(f"ERROR: OCR file not found → {paths['ocr_file']}")

    generate_obsidian_notes(paths["ocr_file"], paths["obsidian_file"], lecture_name)

    print("\n✅ Obsidian (from existing OCR) complete.")


# =====================================================================
# Workflow 4 – anki-full  (A → C → E)
# =====================================================================

def workflow_anki_full(pdf_path: str, module_name: str) -> None:
    """Full Anki workflow: images → relevance → Anki Q&A → .apkg."""
    lecture_name = derive_lecture_name(pdf_path)
    paths = build_output_paths(BASE_OUTPUT_DIR, module_name, lecture_name)
    ensure_dirs(paths)

    # Step A
    image_paths = pdf_to_images(pdf_path, paths["images_dir"])
    page_dict = build_page_dict(image_paths)
    save_page_dict(page_dict, paths["dict_file"])

    # Step E
    client = get_gemini_client()
    page_dict = generate_qa_for_slides(image_paths, page_dict, paths["dict_file"], client=client)
    deck_name = f"{module_name} – {lecture_name}"
    build_anki_package(page_dict, image_paths, deck_name, paths["anki_file"])

    print("\n✅ Anki (full) pipeline complete.")


# =====================================================================
# Workflow 5 – anki-qa  (E: generate Q&A + pack)
# =====================================================================

def workflow_anki_qa(module_name: str, lecture_name: str) -> None:
    """Images & dict exist but Q&A is missing → run LLM + pack .apkg."""
    paths = build_output_paths(BASE_OUTPUT_DIR, module_name, lecture_name)

    if not os.path.isfile(paths["dict_file"]):
        sys.exit(f"ERROR: Dictionary file not found → {paths['dict_file']}")
    if not os.path.isdir(paths["images_dir"]):
        sys.exit(f"ERROR: Images directory not found → {paths['images_dir']}")

    page_dict = _load_page_dict(paths["dict_file"])
    image_paths = _collect_image_paths(paths["images_dir"])

    client = get_gemini_client()
    page_dict = generate_qa_for_slides(image_paths, page_dict, paths["dict_file"], client=client)
    deck_name = f"{module_name} – {lecture_name}"
    build_anki_package(page_dict, image_paths, deck_name, paths["anki_file"])

    print("\n✅ Anki (Q&A + pack) complete.")


# =====================================================================
# Workflow 6 – anki-pack  (E: pack only)
# =====================================================================

def workflow_anki_pack(module_name: str, lecture_name: str) -> None:
    """Dict with Q&A already exists → just build the .apkg file."""
    paths = build_output_paths(BASE_OUTPUT_DIR, module_name, lecture_name)

    if not os.path.isfile(paths["dict_file"]):
        sys.exit(f"ERROR: Dictionary file not found → {paths['dict_file']}")
    if not os.path.isdir(paths["images_dir"]):
        sys.exit(f"ERROR: Images directory not found → {paths['images_dir']}")

    page_dict = _load_page_dict(paths["dict_file"])
    image_paths = _collect_image_paths(paths["images_dir"])

    deck_name = f"{module_name} – {lecture_name}"
    build_anki_package(page_dict, image_paths, deck_name, paths["anki_file"])

    print("\n✅ Anki (pack only) complete.")


# =====================================================================
# Workflow 7 – pdf-only  (A → B)
# =====================================================================

def workflow_pdf_only(pdf_path: str, module_name: str) -> None:
    """Analyse relevance and build the filtered PDF only (no OCR, no LLM)."""
    lecture_name = derive_lecture_name(pdf_path)
    paths = build_output_paths(BASE_OUTPUT_DIR, module_name, lecture_name)
    ensure_dirs(paths)

    # Step A – render pages to images and detect relevance
    image_paths = pdf_to_images(pdf_path, paths["images_dir"])
    page_dict = build_page_dict(image_paths)
    save_page_dict(page_dict, paths["dict_file"])

    # Step B – build the compressed, filtered PDF
    build_relevant_pdf(pdf_path, page_dict, paths["pdf_file"])

    relevant_count = sum(1 for m in page_dict.values() if m.get("is_relevant"))
    print(f"\n✅ PDF-only complete. {relevant_count}/{len(page_dict)} pages marked relevant.")
    print(f"   Saved → {paths['pdf_file']}")

# =====================================================================
# Helper: resolve --pdf / --folder into a list of PDF paths
# =====================================================================

def _resolve_pdfs(args) -> list[str]:
    """Return an ordered list of PDF paths from --pdf or --folder."""
    if hasattr(args, "folder") and args.folder:
        folder = args.folder
        if not os.path.isdir(folder):
            sys.exit(f"ERROR: Folder not found → {folder}")
        pdfs = sorted(
            [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".pdf")]
        )
        if not pdfs:
            sys.exit(f"ERROR: No PDF files found in → {folder}")
        return pdfs
    elif hasattr(args, "pdf") and args.pdf:
        return [args.pdf]
    else:
        sys.exit("ERROR: Either --pdf or --folder is required.")


def _resolve_module(args) -> str:
    """
    Return the module name to use for this run.

    Priority:
      1. Explicit --module value (always wins).
      2. Basename of --folder (automatic extraction).
      3. Error – --pdf was used without --module.
    """
    if args.module:
        return args.module
    if hasattr(args, "folder") and args.folder:
        # Strip trailing separators so basename works reliably.
        module = os.path.basename(os.path.normpath(args.folder))
        print(f"[module] Auto-detected module name from folder: '{module}'")
        return module
    sys.exit("ERROR: --module is required when using --pdf.")


# =====================================================================
# CLI
# =====================================================================

def main():
    """Parse CLI arguments and dispatch to the chosen workflow."""
    parser = argparse.ArgumentParser(
        description="Lecture Extraction – modular pipeline for slides → Obsidian + Anki",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── shared argument groups ──
    def add_pdf_or_folder_arg(p):
        """Add mutually exclusive --pdf / --folder to a subparser."""
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument("--pdf", help="Path to a single input PDF file.")
        group.add_argument("--folder", help="Path to a folder of PDFs (processes all .pdf files).")

    def add_module_arg(p):
        p.add_argument(
            "--module",
            default=None,
            help=(
                "Module / course name. "
                "Optional when --folder is used – defaults to the folder's name."
            ),
        )

    def add_lecture_arg(p):
        p.add_argument("--lecture", required=True, help="Lecture name (without extension).")

    # 1) full
    p_full = subparsers.add_parser("full", help="Run the full pipeline (A→B→C→D→E).")
    add_pdf_or_folder_arg(p_full)
    add_module_arg(p_full)

    # 2) obsidian-scratch
    p_obs_scratch = subparsers.add_parser(
        "obsidian-scratch", help="Obsidian from scratch: PDF → images → OCR → Gemini (A→B→C→D)."
    )
    add_pdf_or_folder_arg(p_obs_scratch)
    add_module_arg(p_obs_scratch)

    # 3) obsidian-existing
    p_obs_exist = subparsers.add_parser(
        "obsidian-existing", help="Obsidian from existing OCR file (D only)."
    )
    add_module_arg(p_obs_exist)
    add_lecture_arg(p_obs_exist)

    # 4) anki-full
    p_anki_full = subparsers.add_parser(
        "anki-full", help="Full Anki workflow: PDF → images → Q&A → .apkg (A→E)."
    )
    add_pdf_or_folder_arg(p_anki_full)
    add_module_arg(p_anki_full)

    # 5) anki-qa
    p_anki_qa = subparsers.add_parser(
        "anki-qa", help="Anki Q&A + pack: images & dict exist → LLM calls → .apkg."
    )
    add_module_arg(p_anki_qa)
    add_lecture_arg(p_anki_qa)

    # 6) anki-pack
    p_anki_pack = subparsers.add_parser(
        "anki-pack", help="Anki pack only: dict with Q&A exists → build .apkg."
    )
    add_module_arg(p_anki_pack)
    add_lecture_arg(p_anki_pack)

    # 7) pdf-only
    p_pdf_only = subparsers.add_parser(
        "pdf-only", help="Analyse relevance and build filtered PDF only (A→B)."
    )
    add_pdf_or_folder_arg(p_pdf_only)
    add_module_arg(p_pdf_only)

    args = parser.parse_args()

    # ── dispatch ──
    if args.command in ("full", "obsidian-scratch", "anki-full", "pdf-only"):
        pdf_list = _resolve_pdfs(args)
        module_name = _resolve_module(args)
        for i, pdf_path in enumerate(pdf_list, 1):
            if len(pdf_list) > 1:
                print(f"\n{'='*60}")
                print(f"  [{i}/{len(pdf_list)}] {os.path.basename(pdf_path)}")
                print(f"{'='*60}")

            if args.command == "full":
                workflow_full(pdf_path, module_name)
            elif args.command == "obsidian-scratch":
                workflow_obsidian_scratch(pdf_path, module_name)
            elif args.command == "anki-full":
                workflow_anki_full(pdf_path, module_name)
            elif args.command == "pdf-only":
                workflow_pdf_only(pdf_path, module_name)

    elif args.command == "obsidian-existing":
        workflow_obsidian_existing(args.module, args.lecture)

    elif args.command == "anki-qa":
        workflow_anki_qa(args.module, args.lecture)

    elif args.command == "anki-pack":
        workflow_anki_pack(args.module, args.lecture)


if __name__ == "__main__":
    main()
