"""
llm_client.py
-------------
Steps D & E of the pipeline (LLM interaction).

Responsibilities:
  - Provide a configured Gemini API client (reads GEMINI_API_KEY
    from the environment).
  - Call Gemini with the raw OCR Markdown to generate structured
    Obsidian notes and save them to
    output/{Module}/Obsidian/obs_{lecture_name}.md (Step D).
  - Call Gemini per slide image to generate Anki Q&A pairs and
    return them as a structured dict (used by Step E).
"""

from google.genai._gaos.utils import unmarshal_json_response
import os

from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel

# ── Tunables ────────────────────────────────────────────────────────
GEMINI_MODEL_OBSIDIAN = "gemini-3.6-flash"  # High-Tier Modell für komplexe Strukturierung
GEMINI_MODEL_ANKI = "gemini-3.6-flash"    # Standard Modell für schnelle Q&A Generierung
ANKI_IMAGE_DPI = 100  # DPI used when scaling slide images sent to Gemini
KI_MAX_CHAPTERS = 10


ANKI_PROMPT = (
    "Create a flashcard Question and Answer based on this lecture slide. "
    "Pay special attention to content marked in green or handwritten "
    "notes in pink. "
    "If nessesary, you can infer additional context from the other slides. "
    "Return the output strictly as JSON matching this schema: "
    '{"question": "<string>", "answer": "<string>"}. '
    "Use the same language the slide is written in."
    "When using equations, use format compatible with Anki"
)

OBSIDIAN_PROMPT = (
    """Du bist ein technischer Assistent zur Datenstrukturierung. 

    <ZIEL>
    Erstelle aus der bereitgestellten JSON-Liste von Folienüberschriften eine strukturierte, vollständige Obsidian-Markdown-Datei. Nutze die Sprache die in der .json verwendet wird!
    </ZIEL>

    <STRIKTE_REGELN>
    1. VOLLSTÄNDIGKEIT: Jeder einzelne Eintrag aus dem JSON muss zwingend in der Ausgabe referenziert werden. Lasse keine einzige Seite aus.
    2. REIHENFOLGE: Die Seitenzahlen sind fortlaufend (1, 2, 3...) und dürfen keine Lücken aufweisen.
    3. HIERARCHIE: Fasse die Seiten sinnvoll zusammen. Erstelle MAXIMAL {KI_MAX_CHAPTERS} Hauptkapitel (##). Nutze bei Bedarf Unterkapitel (###).
    4. WORTLAUT: Verwende die Originaltexte der JSON-Überschriften für deine Kapitel- und Unterkapitelnamen so exakt wie möglich.
    5. FORMATIERUNG: Referenziere die Seiten unter den passenden Überschriften zwingend als Obsidian-PDF-Link im Format `[[{pdf_name}#page=X]]`.
    </STRIKTE_REGELN>

    <BEISPIEL_OUTPUT>
    ## Einführung in die Grundlagen
    [[{pdf_name}#page=1]]
    [[{pdf_name}#page=2]]

    ### Vertiefung und Beispiele
    [[{pdf_name}#page=3]]
    </BEISPIEL_OUTPUT>

    <INPUT_DATEN>
    PDF-Datei: {pdf_name}
    JSON-Überschriften: 
    </INPUT_DATEN>

    Antworte AUSSCHLIESSLICH mit dem validen Markdown-Code. Generiere absolut keinen anderen Text davor oder danach!"""
)

# Pydantic model enforced via Gemini's structured-output feature.
class AnkiCard(BaseModel):
    question: str
    answer: str


def get_gemini_client():
    """
    Initialise and return an authenticated ``google.genai.Client``.

    Key lookup order:
      1. Environment variable ``GEMINI_API_KEY``
      2. File ``key/gemini_key.txt`` in the project root

    Returns:
        A ``genai.Client`` instance ready for content generation.
    """
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        # Fallback: read from key/gemini_key.txt (one level above src/)
        key_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "key", "gemini_key.txt"
        )
        if os.path.isfile(key_file):
            with open(key_file, "r", encoding="utf-8") as fh:
                api_key = fh.read().strip()

    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set and key/gemini_key.txt is empty or missing.\n"
            "Either set the environment variable or paste your key into key/gemini_key.txt."
        )

    client = genai.Client(api_key=api_key)
    return client


def generate_obsidian_notes(
    raw_ocr_path: str,
    output_path: str,
    lecture_name: str,
    client=None,
) -> None:
    """
    Send the raw OCR JSON to Gemini and save the structured
    Obsidian notes.

    Uses the hardcoded OBSIDIAN_PROMPT constant.

    Args:
        raw_ocr_path: Path to the raw OCR JSON file.
        output_path:  Destination for the Obsidian Markdown file
                      (…/Obsidian/obs_{lecture_name}.md).
        lecture_name: Name of the lecture (used to populate the prompt).
        client:       Optional pre-initialised Gemini Client.
    """
    if client is None:
        client = get_gemini_client()

    with open(raw_ocr_path, "r", encoding="utf-8") as fh:
        raw_ocr_text = fh.read()

    # Format the prompt with the module-level constant and the lecture name
    formatted_prompt = OBSIDIAN_PROMPT.format(
        KI_MAX_CHAPTERS=KI_MAX_CHAPTERS,
        pdf_name=f"{lecture_name}.pdf"
    )

    full_prompt = f"{formatted_prompt}\n\n{raw_ocr_text}"

    response = client.models.generate_content(
        model=GEMINI_MODEL_OBSIDIAN,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level="high", 
                include_thoughts=False
            )
        )
    )
    obsidian_md = response.text

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(obsidian_md)

    print(f"[generate_obsidian_notes] Saved → {output_path}")


def generate_anki_qa(
    image_path: str,
    client=None,
) -> dict:
    """
    Send a single slide image to Gemini and return a Q&A pair.

    The image is scaled to 100 DPI in-memory before sending.
    The LLM is instructed to pay special attention to content marked
    in green or handwritten notes in pink.  Gemini's structured-output
    feature (``response_mime_type`` + ``response_schema``) enforces the
    JSON schema ``{"question": str, "answer": str}``.

    Args:
        image_path: Absolute path to the slide image.
        client:     Optional pre-initialised Gemini GenerativeModel.

    Returns:
        Dict with keys ``"question"`` and ``"answer"``.
    """
    if client is None:
        client = get_gemini_client()

    # ── Scale image to 100 DPI in-memory ──
    img = Image.open(image_path)
    # Assume the stored image was rendered at pdf_handler.IMAGE_DPI (200).
    # Scale factor = target / source.
    from pdf_handler import IMAGE_DPI as SOURCE_DPI

    scale = ANKI_IMAGE_DPI / SOURCE_DPI
    new_size = (int(img.width * scale), int(img.height * scale))
    img_scaled = img.resize(new_size, Image.LANCZOS)

    # ── Call Gemini with structured JSON output (Pydantic schema) ──
    response = client.models.generate_content(
        model=GEMINI_MODEL_ANKI,
        contents=[ANKI_PROMPT, img_scaled],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AnkiCard,
        ),
    )

    card: AnkiCard = response.parsed
    return {"question": card.question, "answer": card.answer}

