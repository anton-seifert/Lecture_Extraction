# Lecture Extraction Script Specification

## 1. Overview
This script extracts relevant slides from a PDF slide deck of ONE lecture, creates a compressed PDF of only the relevant slides, generates structured Markdown for Obsidian (with headlines), and creates Anki flashcards.

### Inputs & Configuration
- **Module Name:** Provided manually (e.g., via CLI argument or standard `input()`).
- **Lecture Name:** Extracted from the input PDF file name.
- **API Keys:** Use `GEMINI_API_KEY` from environment variables for Gemini API calls.

## 2. Output Folder Structure
All outputs are saved relative to a base `output/` directory, structured as follows:
```text
output/{Module_name}/
├── images/{lecture_name}/pictures/   # Stores converted images (e.g., pic1.png, pic2.png, etc.)
├── OCR/{lecture_name}_raw.md         # Raw Markdown with OCR text
├── Obsidian/obs_{lecture_name}.md    # Final Obsidian structured notes
├── PDF/result_{lecture_name}.pdf     # Compressed PDF containing only relevant pages
├── Anki/APKG_{lecture_name}.apkg     # Final Anki deck with embedded media
└── dict/{lecture_name}.json          # JSON dictionary holding page metadata
```

## 3. Processing Pipeline

### Step A: Extraction & Image Processing
1. **PDF to Image Conversion:** Convert the input PDF into images (e.g., PNG format). Save these to the `images/{lecture_name}/pictures/` directory.
2. **Relevance Detection:** Analyze the left edge of each image using OpenCV to detect yellow highlights. A slide is considered "relevant" if yellow is detected.
3. **Data Dictionary:** Create a Python dictionary to track page data. 
   - **Key:** `page_number` (int)
   - **Value:** Dictionary `{"is_relevant": bool, "question": "", "answer": ""}`
   - Save this dictionary to `output/{Module_name}/dict/{lecture_name}.json`.
4. **Irrelevant Pages:** Print a list or summary to the console of the pages that were deemed irrelevant (do not open a GUI window that blocks execution).

### Step B: PDF Reconstruction & Compression
1. **Create Sub-PDF:** Using PyMuPDF (`fitz`), create a new PDF containing *only* the relevant pages based on the dictionary.
2. **Compression Logic:** 
   - Initial export: rasterize pages at **100 DPI**.
   - Check file size. If > 5MB, re-export relevant pages at **70 DPI**.
   - If still > 5MB after 70 DPI, print a console warning and save the file as-is.
3. **Save:** Output to `PDF/result_{lecture_name}.pdf`.

### Step C: OCR & Obsidian Markdown
1. **Local OCR:** Run a local OCR tool (`pytesseract`) on the *relevant* images to extract all text.
2. **Stop Word Filtering:** Remove specific unwanted words/phrases from the extracted text (case-insensitive):
   - chapters, slides, page
   - KIT, Karlsruhe Institute of Technology, Karlsruhe Institut of Technology, Karlsruher Institut für Technologie
3. **Raw OCR Output:** Save the filtered text to `OCR/{lecture_name}_raw.md` using the format: `**Slide X** : <extracted_text>\n`

### Step D: LLM Calls
1. **Obsidian Structure Generation:**
   - Make an API call to Gemini (Paid version) passing the raw OCR Markdown file.
   - **Prompt:** is given via variable by user
   - Save output to `Obsidian/obs_{lecture_name}.md`.

### Step E: anki cards
1. **Anki Flashcard Generation:**
   - Iterate through the relevant pages.
   - For each page, pass the image (scaled to 100 DPI in-memory) to Gemini.
   - **Prompt:** Create a flashcard Question and Answer based on the slide, especially relvant are thing marked green or handwritten notes in pink. Return the output strictly matching a JSON schema.
   - Update the dictionary with the generated `question` and `answer`. Save updates to `dict/{lecture_name}.json`.
2. **Anki Packaging (genanki):**
   - Create a genanki Model and Deck.
   - Embed the slide image in the Answer field using HTML (e.g., `<img src="picX.png">`).
   - Ensure the image files are added to the `media_files` list of the genanki `Package`.
   - Save the `.apkg` file to `Anki/APKG_{lecture_name}.apkg`.