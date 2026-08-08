"""
anki_export.py
--------------
Step E of the pipeline.

Responsibilities:
  - Iterate over relevant slides and call the LLM client to generate
    Q&A pairs.
  - Update the page-metadata dictionary with generated questions and
    answers and persist it back to disk.
  - Package the flashcards and embedded slide images into a genanki
    .apkg file saved to output/{Module}/Anki/APKG_{lecture_name}.apkg.
"""

import os
import random

import genanki
from PIL import Image

from llm_client import generate_anki_qa
from pdf_handler import save_page_dict

# ── genanki IDs ─────────────────────────────────────────────────────
# Deterministic but arbitrary IDs required by genanki.
# Using fixed random seeds so the IDs stay stable across runs.
_RNG = random.Random(0x1EC7E42)  # fixed seed for stable IDs across runs
MODEL_ID = _RNG.randrange(1 << 30, 1 << 31)
DECK_ID = _RNG.randrange(1 << 30, 1 << 31)

# ── Card template ───────────────────────────────────────────────────
ANKI_MODEL = genanki.Model(
    MODEL_ID,
    "Lecture Extraction Model",
    fields=[
        {"name": "Question"},
        {"name": "Answer"},
        {"name": "Image"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Question}}",
            "afmt": (
                '{{FrontSide}}<hr id="answer">'
                "<p>{{Answer}}</p>"
                "<br>"
                "{{Image}}"
            ),
        },
    ],
    css="""
.card {
  font-family: arial;
  font-size: 20px;
  text-align: center;
  color: black;
  background-color: white;
}
""",
)


def generate_qa_for_slides(
    image_paths: list[str],
    page_dict: dict,
    dict_output_path: str,
    client=None,
) -> dict:
    """
    Iterate over relevant slides, generate Q&A via the LLM, and
    update *page_dict* in-place, saving it to disk after each update.

    Args:
        image_paths:      Ordered list of all slide image paths.
        page_dict:        Page-metadata dictionary (modified in-place).
        dict_output_path: Path to persist the updated JSON dictionary.
        client:           Optional pre-initialised Gemini GenerativeModel.

    Returns:
        Updated page-metadata dictionary.
    """
    for idx, img_path in enumerate(image_paths):
        page_number = idx + 1  # 1-indexed

        # Lookup – keys may be int (in-memory) or str (from JSON).
        key: int | str
        if page_number in page_dict:
            key = page_number
        elif str(page_number) in page_dict:
            key = str(page_number)
        else:
            continue

        meta = page_dict[key]
        if not meta.get("is_relevant"):
            continue

        print(f"[generate_qa_for_slides] Slide {page_number} …", end=" ", flush=True)

        try:
            qa = generate_anki_qa(img_path, client=client)
            meta["question"] = qa.get("question", "")
            meta["answer"] = qa.get("answer", "")
            print("✓")
        except Exception as exc:
            print(f"✗ ({exc})")
            meta["question"] = ""
            meta["answer"] = ""

        # Persist after every slide so progress survives crashes.
        save_page_dict(page_dict, dict_output_path)

    return page_dict


def build_anki_package(
    page_dict: dict,
    image_paths: list[str],
    deck_name: str,
    output_path: str,
) -> None:
    """
    Create and save a genanki .apkg file from the Q&A data in
    *page_dict*.

    Each card's Answer field embeds the corresponding slide image as:
        <img src="picX.png">

    The image files are included in the genanki Package media_files list.

    Args:
        page_dict:    Page-metadata dictionary containing questions and
                      answers for each relevant page.
        image_paths:  Ordered list of all slide image paths (used to
                      locate image files for embedding).
        deck_name:    Human-readable name for the Anki deck.
        output_path:  Destination path for the .apkg file
                      (…/Anki/APKG_{lecture_name}.apkg).
    """
    deck = genanki.Deck(DECK_ID, deck_name)
    media_files: list[str] = []

    for idx, img_path in enumerate(image_paths):
        page_number = idx + 1

        # Lookup – keys may be int or str.
        meta = page_dict.get(page_number) or page_dict.get(str(page_number))
        if meta is None or not meta.get("is_relevant"):
            continue

        question = meta.get("question", "")
        answer = meta.get("answer", "")

        if not question:
            # Skip slides where LLM failed to produce a Q&A.
            continue

        # Image filename matches the naming convention in pdf_handler.
        image_filename = f"pic{page_number}.png"
        image_html = f'<img src="{image_filename}">'

        # Skaliere das Bild auf 1200x675
        try:
            with Image.open(img_path) as img:
                img_resized = img.resize((1200, 675), Image.LANCZOS)
                img_resized.save(img_path)
        except Exception as e:
            print(f"WARNING: Could not resize image {img_path}: {e}")

        note = genanki.Note(
            model=ANKI_MODEL,
            fields=[question, answer, image_html],
        )
        deck.add_note(note)
        media_files.append(img_path)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    package = genanki.Package(deck)
    package.media_files = media_files
    package.write_to_file(output_path)

    print(
        f"[build_anki_package] {len(deck.notes)} cards, "
        f"{len(media_files)} media files → {output_path}"
    )

