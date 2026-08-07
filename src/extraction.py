#!/usr/bin/env python3
"""
Obsidian Folien Workflow
1. PDF skalieren
2. PDF → Bilder
3. Farberkennung (ganze Seite)
4. Arrays erstellen (GELB + Headlines)
5. resultPDF bauen
6. KI-Aufruf für Markdown
7. Checker
"""

import os
POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin"
os.environ["PATH"] += os.pathsep + POPPLER_PATH

import re
import cv2
import numpy as np
import json
from pathlib import Path
from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter
import subprocess
from pytesseract import pytesseract
from PIL import Image



def scale_pdf(input_path: str, output_path: str, dpi: int) -> str:
    """
    Schritt 1: Skaliert PDF mit Ghostscript - Die ultimative Kombo!
    """
    print(f"📉 Skaliere {input_path} auf {dpi} DPI...")
    # Ersetze "gswin64c" mit dem echten Pfad (Passe die Versionsnummer an deine an):
    GHOSTSCRIPT_PATH = r"C:\Program Files\gs\gs10.07.1\bin\gswin64c.exe"
    
    cmd = [
        GHOSTSCRIPT_PATH,  # <--- HIER GEÄNDERT FÜR WINDOWS!
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
        print(f"✅ Skaliert: {output_path} ({size_kb:.1f} KB)")
        return output_path
    except Exception as e:
        print(f"⚠️  Ghostscript fehlgeschlagen: {e}")
        import shutil
        shutil.copy(input_path, output_path)
        return output_path


def pdf_to_images(pdf_path: str, dpi: int, temp_dir: str) -> tuple:
    """
    Schritt 2: Konvertiert PDF in Bilder
    Args:
        pdf_path: Pfad zur PDF
        dpi: DPI für Bilder
        temp_dir: Temporäres Verzeichnis für Bilder
    Returns:
        (Liste von PIL.Image Objekten, temp_dir)
    """
    print(f"🖼️  Konvertiere {pdf_path} zu Bildern ({dpi} DPI)...")
    os.makedirs(temp_dir, exist_ok=True)
    images = convert_from_path(pdf_path, dpi=dpi)
    print(f"✅ {len(images)} Seiten als Bilder konvertiert")
    return images, temp_dir


def detect_yellow_pages(images: list, temp_dir: str) -> list:
    """
    Schritt 3: Erkennt Seiten mit gelber Markierung (ganze Seite)
    Args:
        images: Liste von PIL.Image Objekten
        temp_dir: Temporäres Verzeichnis für Bilder
    Returns:
        Liste von Indizes der gelben Seiten (0-basiert)
    """
    print("🔍 Suche gelbe Folien (ganze Seite)...")
    yellow_indices = []
    
    for i, img in enumerate(images):
        img_path = f"{temp_dir}/page_{i}.png"
        img.save(img_path)
        
        cv_img = cv2.imread(img_path)
        if cv_img is None:
            print(f"⚠️  Seite {i+1}: Bildfehler")
            continue
        
        hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, LOWER_YELLOW, UPPER_YELLOW)
        
        yellow_pixels = cv2.countNonZero(mask)
        total_pixels = mask.size
        yellow_ratio = yellow_pixels / total_pixels
        
        if yellow_ratio >= YELLOW_THRESHOLD:
            yellow_indices.append(i)
            print(f"  ✅ Seite {i+1}: Gelb ({yellow_ratio*100:.1f}%)")
        else:
            print(f"  ❌ Seite {i+1}: Kein Gelb ({yellow_ratio*100:.1f}%)")
    
    return yellow_indices


def extract_headlines(page_indices: list, temp_dir: str, ocr_area_percent : float) -> list:
    """
    Extrahiere Überschriften per OCR aus den obersten 20% der Folien
    """
    print("📖 Extrahiere Überschriften (OCR auf obersten 20%)...")
    headlines = []

    for new_page_num, original_idx in enumerate(page_indices, start=1):
        # 1. Bild der Seite laden
        img_path = f"{temp_dir}/page_{original_idx}.png"
        img = Image.open(img_path)

        # 2. Oberen Bereich (20%) extrahieren
        width, height = img.size
        top_height = int(height * ocr_area_percent)  # 20% der Höhe
        top_crop = img.crop((0, 0, width, top_height))

        # 3. OCR auf dem Ausschnitt
        title = pytesseract.image_to_string(top_crop, lang='deu+eng').strip()

        # 4. Falls OCR nichts liefert: Fallback
        if not title:
            title = f"Folie {new_page_num}"
        # Definiere Wörter, die entfernt werden sollen

        STRIP_WORDS = ["Kapitel", "Folie", "Seite", "Lektion", "Vorlesung", "Übung", "Thema", "NUT", "NIT", "KIT", "Karlsruhe Institude of Technology", "Karlsruher Institut für Technolgie", "Karlsruhe" ,"@", "Institute of Technology", "NT"]
        title = title.strip()
        for word in STRIP_WORDS:
            title = title.replace(word, "").strip()  # Entferne Wort + Leerzeichen

        headlines.append({"seitenzahl": new_page_num, "text": title})
        print(f"  📌 Seite {new_page_num} (Original {original_idx+1}): '{title}'")

    return headlines


def create_result_pdf(input_path: str, output_path: str, page_indices: list) -> tuple:
    """
    Extrahiert die gelben Seiten aus der ORIGINAL-PDF und wirft toten Code weg.
    """
    import fitz
    print(f"📄 Extrahiere {len(page_indices)} Seiten aus dem Original...")
    
    original_name = Path(input_path).stem
    
    doc = fitz.open(input_path)
    doc.select(page_indices)
    
    # HIER IST DER TRICK: Wir zwingen PyMuPDF, alle Bilder/Schriften der 
    # weggeworfenen Seiten auch WIRKLICH aus der Datei zu löschen!
    doc.save(output_path, garbage=4, deflate=True) 
    doc.close()
    
    return output_path, original_name

def call_ki_for_markdown(headlines: list, pdf_path: str, pdf_name: str, api_key: str = "") -> str:
    """
    Schritt 6: KI-Aufruf für Markdown-Generierung
    Args:
        headlines: Liste von Dicts mit seitenzahl und text
        pdf_path: Pfad zur resultPDF
        pdf_name: Name der resultPDF
    Returns:
        Generierte Markdown als String
    """
    print("🤖 KI-Aufruf für Markdown-Gruppierung...")
    
    prompt = f"""
---
Du bist ein Assistent, der aus **beliebigen Folienüberschriften** eine **vollständige, thematisch strukturierte Obsidian-Markdown-Datei** erstellt.

---

### **STRIKTE REGELN:**
1. **JEDER Eintrag im Input muss in der Markdown vorkommen!** (Keine Seite auslassen!)
2. Die Seitenzahlen sind **konsekutiv** (1, 2, 3, ...) – **keine Lücken!**
3. **Erstelle maximal {KI_MAX_CHAPTERS} Überkapitel (#)**.
   - Nutze **Hierarchien (##, ###, ####)**, um thematische Blöcke zu gruppieren.
   - **Vermeide strikt 1:1-Zuordnung von Folie zu Kapitel!** (!!Kein eigenes Kapitel bzw Unterkapitel pro Folie.!!)
4. So lautet der Pfad der PDF: Z assets/A Study Hub/{MODULUE_NAME}/{pdf_name}

---
### **THEMATISCHE GRUPPIERUNG (WICHTIGSTE REGEL!)**
- **Erkenne automatisch Zusammenhänge** im Input und strukturiere sie logisch: !behalte aber die chronologische reihenfolge der Folien bei!!
  - **Gruppiere Folien mit ähnlichen oder wiederkehrenden Schlüsselbegriffen** (z. B. "Doppelpendel", "Bewegungsgleichungen", "Euler-Lagrange") **unter einem gemeinsamen Kapitel**.
  - **Nutze logische Abfolgen** (z. B. *Theorie → Beispiel → Anwendung → Vertiefung*) für die Hierarchie.
  - halte aber strikt die chronologische Reihenfolge der Zahlen ein, also aufsteigend und springe nicht zwischen diesen hin und her!!
  - Falls der Input eine **Agenda/Overview/Inhaltsfolie** enthält, **orientiere dich strikt an dieser Struktur**.
  - **Beispiel:**
    Wenn Folien zu *"Grundlagen"*, *"Beispiel 1"*, *"Beispiel 2"* aufeinanderfolgen →
    ```markdown
    # Thema X
    ## Grundlagen
    ## Beispiele
    ### Beispiel 1
    ### Beispiel 2
    ```

---
### **WEITERE REGELN:**
4. **Nutze die Originaltexte der Überschriften so nah wie möglich**, aber passe sie **minimal an**, um Hierarchien klar zu machen:
   - Beispiel: Aus `"Beispiel"` → `"Beispiel: Doppelpendel"` (falls der Kontext passt).
5. **Format:**
   Jedes Kapitel/Unterkapitel wird gefolgt von **allen zugehörigen Folien** als `slide-note`-Blöcke.
   Beispiel:
   ```markdown
   ## [Thema]
   ```slide-note
   file: Z assets/A Study Hub/{MODULUE_NAME}/{pdf_name}
   page: X
   ```

---
---
### **BEISPIEL:**
**Input:**
`["seitenzahl: 1, text: Einführung in die Dynamik", "seitenzahl: 2, text: Grundlagen der Bewegungsgleichungen", "seitenzahl: 3, text: Beispiel: Doppelpendel", "seitenzahl: 4, text: Anwendung auf Roboter"]`

**Output:**
```markdown
---
# Dynamik
## Einführung
```slide-note
file: Z assets/A Study Hub/{MODULUE_NAME}/{pdf_name}
page: 1
```
## Grundlagen
```slide-note
file: Z assets/A Study Hub/{MODULUE_NAME}/{pdf_name}
page: 2
```
## Beispiele und Anwendungen
### Beispiel: Doppelpendel
```slide-note
file: Z assets/A Study Hub/{MODULUE_NAME}/{pdf_name}
page: 3
```
### Anwendung auf Roboter
```slide-note
file: Z assets/A Study Hub/{MODULUE_NAME}/{pdf_name}
page: 4
---
```
```

---
---
### **ZIEL DER STRUKTURIERUNG:**
✅ **Thematische Blöcke** (keine isolierten Folien, auch nicht eine Folie pro unterüberschrift oder unterunterüberschrift).
✅ **Hierarchie nutzen** (z. B. `# Thema` → `## Unterthema` → `### Beispiel`).
✅ **Flexibel für alle Themen** (Robotik, Mathe, Programmierung, etc.).
✅ **Originaltexte beibehalten**, aber bei Bedarf präzisieren.

---
### **HINWEIS FÜR DIE KI:**
- **Analysiere den Input auf:**
  - **Wiederkehrende Begriffe** (z. B. "Euler-Lagrange" → gruppiere alle Folien dazu).
  - **Logische Abfolgen** (z. B. Theorie → Beispiel → Vertiefung).
  - **Übergeordnete Themen** (z. B. "Dynamik" als Hauptkapitel für alle Folien zu Bewegungsgleichungen).
- **Vermeide flache Strukturen** – wenn 3+ Folien zu einem Thema gehören, **müssen sie unter einem Kapitel** stehen.
- **Nutze Unterkapitel (###, ####)**, um Beispiele, Schritte oder Vertiefungen zu gliedern.
-einzig die seitenzahlen wo "seite: " davor steht sind relevant
-mach keine quatsch!!!

---
---
**WICHTIG:**
🔹 **Kein Kapitel pro Folie!**
🔹 **Immer thematisch gruppieren!**
🔹 **Funktioniert für JEDEN Folien-Satz** – nicht nur für Euler-Lagrange!
{json.dumps(headlines, ensure_ascii=False)}

**PDF-Pfad:** Z assets/A Study Hub/{MODULUE_NAME}/{pdf_name}

**Antworte NUR mit der Markdown (kein anderer Text!):**"""
    
    
    markdown = None

    try:
        from mistralai.client import Mistral
    except ImportError:
        Mistral = None
        print("mistral import failed")
    
    """api_key = api_key or os.getenv("MISTRAL_API_KEY", "")
    if Mistral is not None and api_key:
        print("requesting Mistral")
        try:
            with Mistral(api_key=api_key) as client:
                response = client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                    response_format={"type": "text"},
                )
                markdown = response.choices[0].message.content
        except Exception as exc:
            print(f"⚠️  Mistral-Aufruf fehlgeschlagen: {exc}")
    """
    if markdown is None:
        print("⚠️  KI-Aufruf nicht verfügbar. Hier wäre der Prompt:")
        print(prompt)

        # Temporäre Lösung: Alle Seiten in ein Kapitel
        markdown = f"# Vorlesungsnotizen\n\n*Quelle: [{pdf_name}]({pdf_name})*\n\n"
        markdown += "## Alle Folien\n\n"
        for headline in headlines:
            markdown += f"[[{pdf_name}#page={headline['seitenzahl']}]]\n\n"

    return markdown


def verify_markdown(markdown: str, num_pages: int) -> bool:
    """
    Schritt 7: Prüft, ob alle Seiten 1..N in Markdown vorkommen
    Args:
        markdown: Generierte Markdown
        num_pages: Anzahl der Seiten in resultPDF
    Returns:
        True, wenn alle Seiten referenziert sind
    """
    print("✅ Verifiziere Seitenzahlen...")
    
    page_refs = re.findall(r'#page=(\d+)', markdown)
    page_refs = [int(p) for p in page_refs]
    
    expected_pages = set(range(1, num_pages + 1))
    actual_pages = set(page_refs)
    
    if expected_pages == actual_pages:
        print(f"  ✅ Alle {num_pages} Seiten korrekt referenziert")
        return True
    else:
        missing = sorted(expected_pages - actual_pages)
        extra = sorted(actual_pages - expected_pages)
        print(f"  ❌ Fehler:")
        if missing:
            print(f"     Fehlend: {missing}")
        if extra:
            print(f"     Extra: {extra}")
        return False


def cleanup(temp_dir: str) -> None:
    """Räumt temporäre Dateien auf"""
    if os.path.exists(temp_dir):
        for f in os.listdir(temp_dir):
            os.remove(f"{temp_dir}/{f}")
        os.rmdir(temp_dir)
        print(f"🧹 Temporäre Dateien gelöscht: {temp_dir}")


# ========== KONFIGURATION (ANPASSBAR) ==========
INPUT_PDF = r"04_Architectures_2026_pre Done.pdf"
MODULUE_NAME = "BioBots"
OUTPUT_DIR = f"{MODULUE_NAME}/output"                    # Ausgabeverzeichnis
SCALE_DPI = 100                          # Ziel-DPI für Skalierung #DPI of 100 is ideal for saving tokens
TEMP_DIR = "temp_images"

# Farbwerte für Gelb (HSV)
LOWER_YELLOW = np.array([20, 50, 200])
UPPER_YELLOW = np.array([35, 255, 255])
YELLOW_THRESHOLD = 0.01                 # 1% der Seite müssen gelb sein

# OCR-Einstellungen
OCR_TOP_PERCENT = 1                   # Oberste 20% der Folie

# KI-Einstellungen
KI_MAX_CHAPTERS = 10

# =============================================

# ========== HAUPTPROGRAMM ==========
def main():
    import linecache

    # API Key laden
    zeile_nr = 1
    key = linecache.getline(r"key\key.txt", zeile_nr)
    MEIN_API_KEY = key.strip()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. PDF -> Bilder (Direkt aus der ORIGINALEN PDF, viel schneller!)
    images, temp_dir = pdf_to_images(INPUT_PDF, SCALE_DPI, temp_dir=TEMP_DIR)
    
    # 2. Gelbe Seiten erkennen
    yellow_indices = detect_yellow_pages(images, temp_dir)
    
    if not yellow_indices:
        print("⚠️  Keine gelben Folien gefunden! Passe YELLOW_THRESHOLD oder Farbwerte an.")
        cleanup(temp_dir)
        return
    
    # 3. Überschriften extrahieren
    headlines = extract_headlines(page_indices=yellow_indices, temp_dir=TEMP_DIR, ocr_area_percent=OCR_TOP_PERCENT)
    
    # Markdown für Headlines speichern
    markdown_path_headlines = f"{OUTPUT_DIR}/headlines/headlines_{Path(INPUT_PDF).stem}.md"
    with open(markdown_path_headlines, "w", encoding="utf-8") as f:
        for entry in headlines:
            f.write(f"Seite {entry['seitenzahl']}: {entry['text']}\n\n")
    print(f"📝 headlines gespeichert: {markdown_path_headlines}")

    # 4. NUR die gelben Seiten aus dem ORIGINAL extrahieren (Temp-PDF)
    temp_extracted_pdf = f"{OUTPUT_DIR}/temp_extracted.pdf"
    _, original_name = create_result_pdf(INPUT_PDF, temp_extracted_pdf, yellow_indices)
    
    # 5. JETZT ERST GHOSTSCRIPT: Brute-Force Kompression der extrahierten Seiten
    result_pdf_name = f"resultPDF_{original_name}.pdf"
    result_pdf_path = f"{OUTPUT_DIR}/result/{result_pdf_name}"
    
    print("🗜️ Wende finale maximale Kompression an...")
    scale_pdf(temp_extracted_pdf, result_pdf_path, SCALE_DPI)
    
    # Temp-PDF aufräumen
    if os.path.exists(temp_extracted_pdf):
        os.remove(temp_extracted_pdf)
    
    # 6. KI für Markdown
    markdown = call_ki_for_markdown(headlines, result_pdf_path, result_pdf_name, api_key=MEIN_API_KEY)
    
    # 7. Markdown speichern
    markdown_path = f"{OUTPUT_DIR}/Obsidian/{original_name}.md"
    os.makedirs(os.path.dirname(markdown_path), exist_ok=True)
    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"📝 Markdown gespeichert: {markdown_path}")
    
    # 8. Checker
    verify_markdown(markdown, len(yellow_indices))
    
    # Aufräumen der Bilder
    # cleanup(temp_dir)
    
    print("\n🎉 Fertig!")
    size_mb = os.path.getsize(result_pdf_path) / (1024 * 1024)
    print(f"   - resultPDF: {result_pdf_path} (Größe: {size_mb:.2f} MB)")
    print(f"   - Markdown: {markdown_path}")

if __name__ == "__main__":
    main()