<h1 align="center">
  <br>
  📄 PDF Translator
  <br>
</h1>

<p align="center">
  <strong>Translate entire PDF documents to Spanish while preserving the original layout, fonts, images, and tables.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0-green?logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/Google%20Translate-API-4285F4?logo=google&logoColor=white" alt="Google Translate">
  <img src="https://img.shields.io/badge/Gemini-AI%20Refinement-8E75B2?logo=google&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/NLP-spaCy-09A3D5?logo=spacy&logoColor=white" alt="spaCy">
  <img src="https://img.shields.io/badge/Spell%20Check-Hunspell-orange" alt="Hunspell">
  <img src="https://img.shields.io/badge/Grammar-LanguageTool-2D6BCC" alt="LanguageTool">
</p>

---

## Overview

PDF Translator is a full-stack web application that translates PDF documents into literary-quality Spanish. It goes beyond simple machine translation by applying a **5-stage NLP post-processing pipeline** that fixes common translation artifacts — literal calques, false friends, incorrect gerund usage, passive voice overuse, and more.

### Key Features

- **Layout preservation** — Converts PDF → DOCX → translates → DOCX → PDF, keeping the original formatting intact
- **Parallel translation** — Multi-threaded paragraph translation with real-time progress tracking
- **5-stage NLP pipeline** — Normalization → Hunspell spellcheck → LanguageTool grammar → spaCy linguistic rules → optional AI refinement
- **200+ linguistic rules** — Custom regex engine fixing false friends, syntactic calques, gerund overuse, passive voice, and idiomatic expressions
- **Optional AI refinement** — Gemini or Claude can polish translations when quality is below threshold
- **Modern UI** — Dark-themed step-by-step interface with drag & drop, progress bars, and confetti on completion

---

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────────────────┐
│  Frontend    │     │  Backend (Flask)                                     │
│  (HTML/JS)  │────▶│                                                      │
│             │     │  Upload ─▶ PDF→DOCX ─▶ Extract paragraphs            │
│  Step 1:    │     │                          │                           │
│   Upload    │     │  Translate ─▶ Google Translate (parallel, 4 workers) │
│             │     │                          │                           │
│  Step 2:    │     │  Post-process ─▶ ┌──────────────────────┐            │
│   Translate │     │                  │ 1. Normalize          │            │
│             │     │                  │ 2. Hunspell spellcheck│            │
│  Step 3:    │     │                  │ 3. LanguageTool grammar│           │
│   Download  │     │                  │ 4. spaCy + regex rules│           │
│             │     │                  │ 5. AI refinement (opt)│            │
└─────────────┘     │                  └──────────────────────┘            │
                    │                          │                           │
                    │  Generate ─▶ Rebuild DOCX ─▶ DOCX→PDF              │
                    └──────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Vanilla HTML/CSS/JS, Syne + DM Sans fonts |
| **Backend** | Python 3.9+, Flask, Flask-CORS |
| **PDF Processing** | pdf2docx, python-docx, fpdf2, PyMuPDF |
| **Translation** | deep-translator (Google Translate) |
| **NLP** | spaCy (es_core_news_sm), Hunspell, LanguageTool API |
| **AI (optional)** | Google Gemini, Anthropic Claude |

---

## Linguistic Post-Processing Pipeline

The core differentiator is the **Spanish literary post-processing engine** (`postprocess_pipeline.py` + `spanish_rules.py`):

| Step | What it fixes | Examples |
|------|--------------|---------|
| **Normalize** | Whitespace, quotes, punctuation, chunking artifacts | `"Hello"` → `—Hola` (Spanish dialogue format) |
| **Hunspell** | Basic Spanish spelling | `habia` → `había` |
| **LanguageTool** | Grammar, punctuation, agreement | Subject-verb agreement, accent marks |
| **Linguistic Rules** | 200+ regex patterns via spaCy | `hace sentido` → `tiene sentido`, `estaba caminando` → `caminaba` |
| **AI Refinement** | Literary polish (only when quality < threshold) | Calques, unnatural phrasing, style |

### Rule Categories (200+ patterns)

- **False friends**: `actualmente` → `en la actualidad`, `realizar` → `darse cuenta`
- **Syntactic calques**: `en orden de` → `para`, `tomar lugar` → `tener lugar`
- **Gerund overuse**: `estaba caminando` → `caminaba`
- **Passive → reflexive**: `fue considerado` → `se consideró`
- **Redundant possessives**: `abrió sus ojos` → `abrió los ojos`
- **Bad collocations**: `sacudió su cabeza` → `negó con la cabeza`
- **Literal idioms**: `llover gatos y perros` → `llover a cántaros`

---

## Getting Started

### Prerequisites

- **Python 3.9+**
- **pip** (Python package manager)

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/pdf-translator.git
cd pdf-translator

# Install dependencies
pip install -r requirements.txt

# Download spaCy Spanish model
python -m spacy download es_core_news_sm
```

### Configuration (Optional)

Copy the example environment file and add your API keys if you want AI-powered refinement:

```bash
cp .env.example .env
```

```env
# Gemini (free tier) — https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_key_here

# Claude (optional, paid) — https://console.anthropic.com
ANTHROPIC_API_KEY=your_key_here
```

> **Note**: Translation works without any API keys using Google Translate. AI keys are only needed for the optional "AI refinement" feature.

### Run

```bash
# Option 1: Direct
cd backend
python app.py

# Option 2: Start script (installs deps automatically)
# Windows
start.bat

# macOS / Linux
chmod +x start.sh
./start.sh
```

Open **http://localhost:5000** in your browser.

---

## Usage

1. **Upload** — Drag & drop or select a PDF file. The app automatically converts it to DOCX preserving layout.
2. **Translate** — Choose the source language (or auto-detect) and click "Traducir documento". Watch real-time progress.
3. **Download** — The translated DOCX is converted back to PDF. Download the result.

---

## Project Structure

```
pdf-translator/
├── backend/
│   ├── app.py                    # Flask server + API routes + translation engine
│   ├── postprocess_pipeline.py   # 5-stage NLP pipeline (normalize → hunspell → LT → spaCy → AI)
│   ├── spanish_rules.py          # 200+ linguistic rules (false friends, calques, gerunds, passive)
│   └── dicts/                    # Hunspell Spanish dictionaries (es_ES.aff, es_ES.dic)
├── frontend/
│   └── index.html                # Single-page UI (dark theme, step wizard)
├── tests/
│   ├── test_e2e_translate.py     # End-to-end translation tests
│   ├── test_hang_fix.py          # Timeout / deadlock regression tests
│   └── test_postprocess.py       # Post-processing pipeline unit tests
├── .env.example                  # Environment template
├── requirements.txt              # Python dependencies
├── start.bat                     # Windows launcher
├── start.sh                      # macOS/Linux launcher
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload PDF, auto-convert to DOCX |
| `GET` | `/api/paragraphs/:id` | Get extracted paragraphs |
| `POST` | `/api/translate-docx` | Start background translation job |
| `GET` | `/api/translate-progress/:id` | Poll translation progress |
| `POST` | `/api/translate-cancel/:id` | Cancel active translation |
| `POST` | `/api/generate-pdf` | Convert translated DOCX → PDF |
| `GET` | `/api/download/:id/:file` | Download translated file |

---

## License

MIT

---

<p align="center">
  Built with Python, Flask, and a lot of regex.
</p>
