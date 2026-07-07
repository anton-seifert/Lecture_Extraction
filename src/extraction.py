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
import re
import cv2
import numpy as np
import json
from pathlib import Path
from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter
import subprocess



def scale_pdf(input_path: str, output_path: str, dpi: int = SCALE_DPI) -> str:
    """
    Schritt 1: Skaliert PDF mit Ghostscript
    Args:
        input_path: Pfad zur Eingabe-PDF
        output_path: Pfad zur skalierten PDF
        dpi: Ziel-DPI (Standard: SCALE_DPI)
    Returns:
        Pfad zur skalierten PDF
    """
    print(f"📉 Skaliere {input_path} auf {dpi} DPI...")
    cmd = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dPDFSETTINGS=/screen",
        f"-r{dpi}",
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


def pdf_to_images(pdf_path: str, dpi: int = SCALE_DPI, temp_dir: str = "temp_images") -> tuple:
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


def extract_headlines(pdf_path: str, page_indices: list) -> list:
    """
    Schritt 4: Extrahiere Überschriften von gelben Seiten
    Args:
        pdf_path: Pfad zur PDF
        page_indices: Liste von Original-Seitenindizes (0-basiert)
    Returns:
        Liste von Dicts: [{"seitenzahl": 1, "text": "Überschrift"}, ...]
        (seitenzahl = neue konsekutive Nummer: 1, 2, 3, ...)
    """
    print("📖 Extrahiere Überschriften (oberste Zeilen)...")
    
    reader = PdfReader(pdf_path)
    headlines = []
    
    for new_page_num, original_idx in enumerate(page_indices, start=1):
        page = reader.pages[original_idx]
        text = page.extract_text()
        
        if text:
            lines = text.split('\n')
            for line in lines:
                if line.strip():
                    title = line.strip()
                    title = re.sub(r'^\d+\s*', '', title)
                    title = re.sub(r'\s*\d+$', '', title)
                    headlines.append({"seitenzahl": new_page_num, "text": title})
                    print(f"  📌 Neue Seite {new_page_num} (Original {original_idx+1}): '{title}'")
                    break
        else:
            headlines.append({"seitenzahl": new_page_num, "text": f"Folie {new_page_num}"})
    
    return headlines


def create_result_pdf(input_path: str, output_path: str, page_indices: list) -> tuple:
    """
    Schritt 5: Erstellt resultPDF aus gelben Seiten
    Args:
        input_path: Pfad zur Eingabe-PDF
        output_path: Pfad zur resultPDF
        page_indices: Liste von Original-Seitenindizes (0-basiert)
    Returns:
        (Pfad zur resultPDF, originaler Name)
    """
    print(f"📄 Erstelle resultPDF aus {len(page_indices)} Seiten...")
    
    original_name = Path(input_path).stem
    
    reader = PdfReader(input_path)
    writer = PdfWriter()
    
    for idx in page_indices:
        writer.add_page(reader.pages[idx])
    
    with open(output_path, "wb") as f:
        writer.write(f)
    
    size_kb = os.path.getsize(output_path) / 1024
    print(f"✅ resultPDF: {output_path} ({size_kb:.1f} KB)")
    return output_path, original_name


def call_ki_for_markdown(headlines: list, pdf_path: str, pdf_name: str) -> str:
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
    
    prompt = f"""Du bist ein Assistent, der aus Folienüberschriften eine **vollständige Obsidian-Markdown-Datei** erstellt.

**STRIKTE REGELN:**
1. **JEDER Eintrag im Input muss in der Markdown vorkommen!** (Keine Seite auslassen!)
2. Die Seitenzahlen im Input sind **konsekutiv** (1, 2, 3, ...) - **keine Lücken!**
3. Erstelle **maximal {KI_MAX_CHAPTERS} Überkapitel** (##), gerne mit Unterkapiteln (###).
4. Nutze die Originaltexte der Überschriften so nah wie möglich.
5. Format: ## [Kapitel]\\n[[{pdf_name}#page=1]]\\n[[{pdf_name}#page=2]]\\n...

**BEISPIEL:**
Input: ["seitenzahl: 1, text: Einführung", "seitenzahl: 2, text: Grundlagen", "seitenzahl: 3, text: Beispiel"]
Output:
## Einführung
[[{pdf_name}#page=1]]

## Grundlagen
[[{pdf_name}#page=2]]

## Beispiele
[[{pdf_name}#page=3]]

**JETZT ERSTELLE DIE MARKDOWN FÜR DIESEN INPUT:**
{json.dumps(headlines, ensure_ascii=False)}

**PDF-Pfad:** {pdf_path}
**Antworte NUR mit der Markdown (kein anderer Text!):**"""
    
    # HIER KI-AUFRUF EINFÜGEN
    # Beispiel mit Mistral API:
    # from mistralai.client import MistralClient
    # client = MistralClient(api_key="DEIN_API_KEY")
    # response = client.chat(model="mistral-medium", messages=[{"role": "user", "content": prompt}])
    # markdown = response.choices[0].message.content
    
    # Für Testzwecke: Einfache Markdown ohne KI
    print("⚠️  KI-Aufruf nicht implementiert. Hier wäre der Prompt:")
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
INPUT_PDF = "C:\Users\Anton Admin\Coding\Lecture_Extraction\Robotics-I-Chapter-04-Dynamics Copy.pdf"
OUTPUT_DIR = "output"                    # Ausgabeverzeichnis
SCALE_DPI = 150                          # Ziel-DPI für Skalierung

# Farbwerte für Gelb (HSV)
LOWER_YELLOW = np.array([20, 50, 200])
UPPER_YELLOW = np.array([35, 255, 255])
YELLOW_THRESHOLD = 0.02                 # 2% der Seite müssen gelb sein

# OCR-Einstellungen
OCR_TOP_PERCENT = 0.2                   # Oberste 20% der Folie

# KI-Einstellungen
KI_MAX_CHAPTERS = 10
# =============================================

# ========== HAUPTPROGRAMM ==========
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. PDF skalieren
    scaled_pdf = f"{OUTPUT_DIR}/scaled_{INPUT_PDF}"
    scale_pdf(INPUT_PDF, scaled_pdf)
    
    # 2. PDF → Bilder
    images, temp_dir = pdf_to_images(scaled_pdf)
    
    # 3. Gelbe Seiten erkennen
    yellow_indices = detect_yellow_pages(images, temp_dir)
    
    if not yellow_indices:
        print("⚠️  Keine gelben Folien gefunden! Passe YELLOW_THRESHOLD oder Farbwerte an.")
        cleanup(temp_dir)
        return
    
    # 4. Überschriften extrahieren
    headlines = extract_headlines(scaled_pdf, yellow_indices)
    
    # 5. resultPDF erstellen
    result_pdf_name = f"resultPDF_{Path(INPUT_PDF).stem}.pdf"
    result_pdf_path = f"{OUTPUT_DIR}/{result_pdf_name}"
    result_pdf_path, original_name = create_result_pdf(scaled_pdf, result_pdf_path, yellow_indices)
    
    # 6. KI für Markdown
    markdown = call_ki_for_markdown(headlines, result_pdf_path, result_pdf_name)
    
    # 7. Markdown speichern
    markdown_path = f"{OUTPUT_DIR}/notizen_{original_name}.md"
    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"📝 Markdown gespeichert: {markdown_path}")
    
    # 8. Checker
    verify_markdown(markdown, len(yellow_indices))
    
    # Aufräumen
    #cleanup(temp_dir)
    
    print("\n🎉 Fertig!")
    print(f"   - Skalierte PDF: {scaled_pdf}")
    print(f"   - resultPDF: {result_pdf_path}")
    print(f"   - Markdown: {markdown_path}")


if __name__ == "__main__":
    main()