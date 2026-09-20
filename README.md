# Lecture Extraction

A CLI pipeline that processes lecture PDFs into filtered, compressed PDFs, structured Obsidian notes, and Anki flashcard decks.

---

## Prerequisites

| Dependency | Notes |
|---|---|
| Python 3.10+ | |
| [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) | Add to system PATH |
| [Ghostscript](https://www.ghostscript.com/releases/gsdnld.html) | Required for PDF compression fallback. Default path: `C:\Program Files\gs\gs10.07.1\bin\gswin64c.exe` – update `GHOSTSCRIPT_PATH` in `pdf_handler.py` if your version differs. |
| Gemini API Key | Place your key in `key/gemini_key.txt` (or set `GEMINI_API_KEY` env var) |

Install Python dependencies:
```bash
pip install -r requirements.txt
```

---

## Relevance Detection

The pipeline identifies **relevant slides** by detecting a **yellow highlight on the left edge** of the slide (e.g. a coloured marker strip in your PDF viewer). Only slides with this marker will be processed.

- Tune sensitivity via `LEFT_EDGE_RATIO` and `YELLOW_PIXEL_THRESHOLD` in `pdf_handler.py`.

---

## CLI Commands

All commands are run from the project root. You can pass either a single PDF (`--pdf`) or an entire folder of PDFs (`--folder`). When using `--folder`, the module name is automatically derived from the folder name unless `--module` is specified explicitly.

### `full` — Complete pipeline
Renders images → detects relevance → builds filtered PDF → OCR → Obsidian notes → Anki deck.

```bash
python src/main.py full --pdf "Originals/lecture.pdf" --module "MyModule"
python src/main.py full --folder "Originals/robotics II" --module "robotics_II"
```

### `pdf-only` — Filtered PDF only
Renders images, detects relevance, builds a compressed filtered PDF. No OCR or LLM involved.

```bash
python src/main.py pdf-only --pdf "Originals/lecture.pdf" --module "MyModule"
python src/main.py pdf-only --folder "Originals/robotics II"
```

### `obsidian-scratch` — Obsidian notes from a fresh PDF
Renders images → PDF → OCR → Gemini structured notes.

```bash
python src/main.py obsidian-scratch --pdf "Originals/lecture.pdf" --module "MyModule"
```

### `obsidian-existing` — Obsidian notes from existing OCR
Requires an already generated OCR JSON file (from a previous run).

```bash
python src/main.py obsidian-existing --module "MyModule" --lecture "Lecture_01"
```

### `anki-full` — Full Anki deck from PDF
Renders images → detects relevance → LLM generates Q&A → exports `.apkg`.

```bash
python src/main.py anki-full --pdf "Originals/lecture.pdf" --module "MyModule"
```

### `anki-qa` — Generate Q&A for existing images
Images and dict file already exist; runs only the LLM calls and packages the deck.

```bash
python src/main.py anki-qa --module "MyModule" --lecture "Lecture_01"
```

### `anki-pack` — Pack existing Q&A into `.apkg`
Dict with Q&A already populated; just builds the Anki package.

```bash
python src/main.py anki-pack --module "MyModule" --lecture "Lecture_01"
```

---

## Output Structure

```
output/
└── {module}/
    ├── images/{lecture}/pictures/   # Rendered slide images (pic1.png, …)
    ├── dict/{lecture}.json          # Page metadata (relevance, Q&A pairs)
    ├── OCR/{lecture}_raw.json       # Raw OCR text per relevant slide
    ├── PDF/result_{lecture}.pdf     # Filtered, compressed PDF
    ├── Obsidian/obs_{lecture}.md    # Structured Obsidian note
    └── Anki/APKG_{lecture}.apkg    # Anki flashcard deck
```

---

## How It Works

The pipeline is split into five steps (A–E):

```
PDF
 │
 ▼ Step A — pdf_handler.py
   Render each page to a PNG at 200 DPI using PyMuPDF.
   Detect relevance: scan the leftmost 7% of each image for yellow pixels (HSV mask).
   Save a page-metadata JSON (dict).
 │
 ▼ Step B — pdf_handler.py
   Native vector extraction with PyMuPDF (doc.select()).
   If > 5 MB: scale embedded images via Ghostscript at 100 DPI → 70 DPI.
 │
 ▼ Step C — ocr_processor.py
   Run Tesseract OCR (deu+eng) on each relevant slide image.
   Filter out stop-words / institutional boilerplate.
   Save result as a JSON list: [{slide: N, text: "..."}, ...]
 │
 ▼ Step D — llm_client.py (Gemini Pro, thinking_level=high)
   Send the OCR JSON + a structured prompt to Gemini.
   Receive a complete Obsidian Markdown file with chapter headings
   and PDF page links in the format [[lecture.pdf#page=N]].
 │
 ▼ Step E — anki_export.py + llm_client.py (Gemini Flash)
   For each relevant slide, send the image to Gemini → generate Q&A pair.
   Resize the slide image to 1200×675 px.
   Package all cards + images into a genanki .apkg file.
```
