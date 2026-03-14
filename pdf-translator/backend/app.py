"""
PDF Translator - Backend Flask v2
Mejoras:
  - Gemini 1.5 Flash como motor de IA (tier gratuito muy generoso)
  - Conversión automática de comillas "texto" → —texto (diálogos español)
  - Preservación de imágenes del PDF original en el PDF final
"""

import os
import re
import json
import uuid
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).parent.parent
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# SESIONES
# ─────────────────────────────────────────────

def get_session_path(session_id):
    p = SESSIONS_DIR / session_id
    p.mkdir(exist_ok=True)
    return p

def save_session_meta(session_id, data):
    path = get_session_path(session_id) / "meta.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_session_meta(session_id):
    path = get_session_path(session_id) / "meta.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# ─────────────────────────────────────────────
# POST-PROCESAMIENTO DE TEXTO (Español literario)
# ─────────────────────────────────────────────

def post_process_spanish(text):
    """
    Pipeline completo de post-procesamiento para texto literario en español.
    Aplica todas las correcciones en orden lógico.
    """
    text = fix_whitespace(text)
    text = fix_dialogues(text)
    text = fix_punctuation_spacing(text)
    text = capitalize_after_period(text)
    text = fix_opening_marks(text)
    text = fix_paragraph_structure(text)
    text = fix_ellipsis(text)
    text = fix_ordinals(text)
    return text


# ── 1. ESPACIADO Y LIMPIEZA BÁSICA ──────────

def fix_whitespace(text):
    """Limpia espacios duplicados, tabulaciones erróneas y líneas vacías excesivas."""
    # Reemplazar tabulaciones por espacio
    text = text.replace('\t', ' ')
    # Múltiples espacios → uno solo (no tocar saltos de línea)
    text = re.sub(r'[^\S\n]+', ' ', text)
    # Espacio al final de línea
    text = re.sub(r' +\n', '\n', text)
    # Espacio al inicio de línea (excepto indentación intencional de diálogos)
    text = re.sub(r'\n +(?!—)', '\n', text)
    # Más de 2 líneas vacías consecutivas → máximo 2
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip()


# ── 2. DIÁLOGOS (COMILLAS → GUIÓN LARGO) ────

def fix_dialogues(text):
    """
    Convierte diálogos con comillas al formato español con guión largo (—).
    Dos pasadas: primero por línea (diálogos completos), luego limpieza inline.
    """
    lines = text.split('\n')
    result = []
    for line in lines:
        line = _convert_dialogue_line(line)
        result.append(line)
    text = '\n'.join(result)
    # Segunda pasada: comillas sueltas que quedaron inline
    text = _cleanup_remaining_quotes(text)
    return text


def _cleanup_remaining_quotes(text):
    """Convierte cualquier comilla de diálogo que haya quedado suelta."""
    # "texto" o \u201ctexto\u201d o «texto» → —texto (inline)
    text = re.sub(r'["\u201c\u00ab]([^"\u201d\u00bb\n]+?)["\u201d\u00bb]', r'—\1', text)
    # Comillas francesas huérfanas
    text = text.replace('\u00ab', '\u2014').replace('\u00bb', '')
    # Comillas tipográficas huérfanas
    text = text.replace('\u201c', '\u2014').replace('\u201d', '')
    return text


def _convert_dialogue_line(line):
    """Procesa una línea individual para convertir comillas en guiones largos."""
    stripped = line.strip()
    if not stripped:
        return line

    # Patrón: línea completa es un diálogo entre comillas con posible inciso
    # Ejemplo: "Hola", dijo Juan, "¿cómo estás?"
    # Ejemplo: «Hola», dijo Juan, «¿cómo estás?»
    OPEN_Q = r'[\"\u201c\u00ab]'
    CLOSE_Q = r'[\"\u201d\u00bb]'

    # Caso 1: Diálogo con inciso del narrador al final
    # "Texto del diálogo", dijo/exclamó/preguntó/respondió...
    m = re.match(
        rf'^{OPEN_Q}(.+?){CLOSE_Q}\s*[,.]?\s*'
        rf'(\b(?:dijo|exclamó|preguntó|respondió|susurró|gritó|murmuró|añadió|'
        rf'contestó|replicó|comentó|afirmó|negó|insistió|suplicó|ordenó|'
        rf'interrumpió|continuó|prosiguió|explicó|señaló|indicó|sugirió|'
        rf'pensó|reflexionó|musitó|balbuceó|tartamudeó|chilló|bramó|'
        rf'said|asked|replied|whispered|shouted|exclaimed|answered|added|'
        rf'murmured|cried|called|screamed|yelled|demanded|insisted)\b.*)$',
        stripped, re.IGNORECASE
    )
    if m:
        dialogo = m.group(1)
        inciso = m.group(2)
        return f'—{dialogo} —{inciso}'

    # Caso 2: Diálogo con inciso intercalado
    # "Hola", dijo Juan. "¿Cómo estás?"
    m2 = re.match(
        rf'^{OPEN_Q}(.+?){CLOSE_Q}\s*[,.]?\s*(.+?)\s*[,.]?\s*{OPEN_Q}(.+?){CLOSE_Q}\s*$',
        stripped
    )
    if m2:
        d1 = m2.group(1)
        inciso = m2.group(2)
        d2 = m2.group(3)
        # Verificar si el inciso contiene verbo dicendi
        if re.search(r'\b(dijo|exclamó|preguntó|respondió|susurró|gritó|murmuró|añadió|'
                     r'said|asked|replied|whispered)\b', inciso, re.IGNORECASE):
            return f'—{d1} —{inciso}—. {d2}'
        return f'—{d1} —{inciso}—. {d2}'

    # Caso 3: Línea completa entre comillas (diálogo simple)
    m3 = re.match(rf'^{OPEN_Q}(.+?){CLOSE_Q}\s*([.!?]?)\s*$', stripped)
    if m3:
        contenido = m3.group(1)
        punct_final = m3.group(2)
        # Si el contenido ya termina en puntuación, no duplicar
        if contenido and contenido[-1] in '.!?¡¿':
            return f'—{contenido}'
        return f'—{contenido}{punct_final}'

    # Caso 4: Línea que EMPIEZA con comilla de apertura (diálogo parcial,
    # la comilla de cierre puede estar más adelante o no existir)
    if re.match(rf'^{OPEN_Q}', stripped):
        # Quitar comilla de apertura, poner guión largo
        line_new = re.sub(rf'^{OPEN_Q}', '—', stripped)
        # Quitar comilla de cierre si es la última cosa en la línea
        line_new = re.sub(rf'{CLOSE_Q}\s*$', '', line_new)
        # Comillas restantes sueltas → guiones de inciso
        line_new = re.sub(rf'{CLOSE_Q}\s*[,.]?\s*', ' —', line_new)
        line_new = re.sub(rf'\s*{OPEN_Q}', '— ', line_new)
        return line_new

    # Caso 5: Comillas francesas sueltas restantes
    if '«' in line or '»' in line:
        line = re.sub(r'«(.+?)»', lambda m: f'—{m.group(1)}', line)
        line = line.replace('«', '—').replace('»', '')

    return line


# ── 3. SIGNOS DE APERTURA ¿ ¡ ──────────────

def fix_opening_marks(text):
    """
    Añade signos de apertura ¿ y ¡ cuando faltan.
    En español es obligatorio: ¿Cómo estás? ¡Increíble!
    Detecta oraciones interrogativas/exclamativas y añade el signo de apertura.
    """
    lines = text.split('\n')
    result = []
    for line in lines:
        line = _fix_opening_marks_line(line)
        result.append(line)
    return '\n'.join(result)


def _fix_opening_marks_line(line):
    """Corrige signos de apertura en una línea."""
    # Caso: oración que termina en ? pero no tiene ¿
    # Acepta inicio en mayúscula O minúscula, después de espacio/inicio de línea
    line = re.sub(
        r'(?<![¿\w])([A-Za-zÁÉÍÓÚÑáéíóúñ¿][^.!?¡¿]*?\?)',
        lambda m: _insert_opening_question(m.group(1)),
        line
    )
    # Caso: oración que termina en ! pero no tiene ¡
    line = re.sub(
        r'(?<![¡\w])([A-Za-zÁÉÍÓÚÑáéíóúñ¡][^.!?¡¿]*?!)',
        lambda m: _insert_opening_exclamation(m.group(1)),
        line
    )
    return line


def _insert_opening_question(segment):
    """Inserta ¿ al inicio de un segmento interrogativo si no lo tiene."""
    if '¿' in segment:
        return segment
    return '¿' + segment


def _insert_opening_exclamation(segment):
    """Inserta ¡ al inicio de un segmento exclamativo si no lo tiene."""
    if '¡' in segment:
        return segment
    return '¡' + segment


# ── 4. ESPACIADO Y PUNTUACIÓN ───────────────

def fix_punctuation_spacing(text):
    """
    Corrige problemas comunes de espaciado con puntuación:
      - Quita espacio ANTES de . , ; : ? ! ) ] »
      - Asegura espacio DESPUÉS de . , ; : ? ! ( [ «
      - Quita espacio DESPUÉS de ( [ « ¿ ¡
      - No separa puntos suspensivos
      - No toca el guión largo + espacio (formato de diálogo)
    """
    # Espacio antes de puntuación de cierre → quitar
    text = re.sub(r' +([.,;:?!)\]»])', r'\1', text)

    # Espacio después de puntuación de apertura → quitar
    text = re.sub(r'([([«¿¡]) +', r'\1', text)

    # Asegurar espacio después de puntuación de cierre si sigue letra/número
    # (excepto dentro de números como 1.000 o URLs)
    text = re.sub(r'([.,;:?!])([A-Za-záéíóúñÁÉÍÓÚÑ])', r'\1 \2', text)

    # Punto + mayúscula sin espacio (ej: "fin.Inicio")
    text = re.sub(r'\.([A-ZÁÉÍÓÚÑ])', r'. \1', text)

    # Coma pegada a la siguiente palabra sin espacio
    text = re.sub(r',([a-záéíóúñA-ZÁÉÍÓÚÑ])', r', \1', text)

    # Puntos suspensivos: normalizar variantes
    text = re.sub(r'\.\s*\.\s*\.', '...', text)

    # Doble puntuación accidental (.. →  .  ,,  →  ,)
    text = re.sub(r'([.])\1(?!\.)', r'\1', text)  # .. → . (pero no ... → ..)
    text = re.sub(r',,+', ',', text)
    text = re.sub(r';;+', ';', text)

    return text


# ── 5. MAYÚSCULAS DESPUÉS DE PUNTO ──────────

def capitalize_after_period(text):
    """
    Asegura mayúscula después de:
      - Punto seguido + espacio
      - Puntos suspensivos + espacio
      - Cierre de interrogación/exclamación + espacio
      - Inicio de cada línea/párrafo
      - Después de guión largo de diálogo
    """
    # Después de . ? ! + espacio
    text = re.sub(r'([.?!]) (\w)', lambda m: m.group(1) + ' ' + m.group(2).upper(), text)
    # Después de puntos suspensivos + espacio
    text = re.sub(r'(\.{3}) (\w)', lambda m: m.group(1) + ' ' + m.group(2).upper(), text)
    # Después de guión largo de diálogo al inicio de línea
    text = re.sub(r'(^|\n)(—)(\w)', lambda m: m.group(1) + '—' + m.group(3).upper(), text)
    # Inicio de cada línea
    lines = text.split('\n')
    fixed = []
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            indent = line[:len(line) - len(stripped)]
            if stripped.startswith('—'):
                # No tocar la mayúscula si es diálogo (ya se manejó)
                fixed.append(indent + stripped)
            else:
                fixed.append(indent + stripped[0].upper() + stripped[1:])
        else:
            fixed.append(line)
    return '\n'.join(fixed)


# ── 6. ESTRUCTURA DE PÁRRAFOS ───────────────

def fix_paragraph_structure(text):
    """
    Reconstruye la estructura de párrafos que se pierde
    en la extracción de PDF. Detecta:
      - Líneas cortas que son fin de párrafo (no llenan el ancho)
      - Cambios de escena (líneas con *** o similar)
      - Encabezados de capítulo
      - Diálogos que deben ser párrafos separados
    """
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Línea vacía → preservar como separador de párrafo
        if not stripped:
            result.append('')
            i += 1
            continue

        # Separadores de escena: ***, ---, ===, • • •, etc.
        if re.match(r'^[\s*\-=•~─—_]{3,}$', stripped):
            result.append('')
            result.append('* * *')
            result.append('')
            i += 1
            continue

        # Posible encabezado de capítulo
        if _is_chapter_heading(stripped):
            if result and result[-1] != '':
                result.append('')
            result.append(stripped)
            result.append('')
            i += 1
            continue

        # Diálogos (líneas con —) siempre son párrafo aparte
        if stripped.startswith('—'):
            if result and result[-1] != '' and not result[-1].startswith('—'):
                result.append('')
            result.append(stripped)
            i += 1
            continue

        # Línea normal de texto narrativo
        result.append(stripped)
        i += 1

    # Limpiar líneas vacías excesivas generadas por la reestructuración
    cleaned = '\n'.join(result)
    cleaned = re.sub(r'\n{4,}', '\n\n\n', cleaned)
    return cleaned


def _is_chapter_heading(line):
    """Detecta si una línea es un encabezado de capítulo."""
    patterns = [
        r'^(?:Capítulo|CAPÍTULO|Chapter|CHAPTER)\s+[\dIVXLCDMivxlcdm]+',
        r'^(?:PARTE|Parte|Part|PART)\s+[\dIVXLCDMivxlcdm]+',
        r'^(?:Prólogo|PRÓLOGO|Epílogo|EPÍLOGO|Prologue|Epilogue)',
        r'^(?:LIBRO|Libro|Book|BOOK)\s+[\dIVXLCDMivxlcdm]+',
        r'^[IVXLCDM]+\s*$',  # Numerales romanos solos
        r'^\d+\s*$',  # Número solo (capítulo)
    ]
    return any(re.match(p, line, re.IGNORECASE) for p in patterns)


# ── 7. PUNTOS SUSPENSIVOS ──────────────────

def fix_ellipsis(text):
    """Normaliza puntos suspensivos: exactamente 3 puntos, sin espacio entre ellos."""
    # 2 puntos → 3 (es un error común)
    text = re.sub(r'(?<!\.)\.{2}(?!\.)', '...', text)
    # 4+ puntos → 3
    text = re.sub(r'\.{4,}', '...', text)
    # Espacio después de puntos suspensivos si sigue letra
    text = re.sub(r'(\.\.\.)([A-Za-záéíóúñÁÉÍÓÚÑ])', r'\1 \2', text)
    return text


# ── 8. ORDINALES EN ESPAÑOL ────────────────

def fix_ordinals(text):
    """Convierte ordinales en inglés a formato español: 1st → 1.º, 2nd → 2.ª (contexto general)."""
    text = re.sub(r'\b(\d+)(?:st|nd|rd|th)\b', r'\1.º', text)
    return text

# ─────────────────────────────────────────────
# EXTRACCIÓN DE IMÁGENES
# ─────────────────────────────────────────────

def extract_images_from_pdf(pdf_path, output_dir):
    """Extrae imágenes del PDF y devuelve lista con info de posición."""
    images_info = []
    try:
        from pypdf import PdfReader
        from PIL import Image as PILImage
        import io

        reader = PdfReader(str(pdf_path))

        for page_num, page in enumerate(reader.pages):
            resources = page.get("/Resources")
            if not resources:
                continue
            xobjects = resources.get("/XObject")
            if not xobjects:
                continue
            xobjects = xobjects.get_object()

            img_idx = 0
            for key, obj in xobjects.items():
                obj = obj.get_object()
                if obj.get("/Subtype") != "/Image":
                    continue
                try:
                    width_px = int(obj.get("/Width", 100))
                    height_px = int(obj.get("/Height", 100))
                    color_space = obj.get("/ColorSpace", "/DeviceRGB")
                    if isinstance(color_space, list):
                        color_space = color_space[0]
                    mode = "L" if color_space == "/DeviceGray" else "RGB"

                    data = obj.get_data()
                    pil_img = PILImage.frombytes(mode, (width_px, height_px), data)

                    img_filename = f"img_p{page_num+1}_{img_idx}.png"
                    img_path = output_dir / img_filename
                    pil_img.save(str(img_path))

                    images_info.append({
                        "page": page_num,
                        "index": img_idx,
                        "path": str(img_path),
                        "filename": img_filename,
                        "width_px": width_px,
                        "height_px": height_px,
                    })
                    img_idx += 1
                except Exception as e:
                    print(f"  Imagen omitida p{page_num+1}/{key}: {e}")
    except Exception as e:
        print(f"Advertencia extrayendo imágenes: {e}")

    print(f"Imágenes extraídas: {len(images_info)}")
    return images_info

# ─────────────────────────────────────────────
# 1. SUBIR PDF
# ─────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "El archivo debe ser un PDF"}), 400

    session_id = str(uuid.uuid4())
    session_path = get_session_path(session_id)
    pdf_path = session_path / "original.pdf"
    file.save(str(pdf_path))

    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    meta = {
        "session_id": session_id,
        "original_filename": file.filename,
        "total_pages": total_pages,
        "parts": [],
        "status": "uploaded"
    }
    save_session_meta(session_id, meta)
    return jsonify({"session_id": session_id, "filename": file.filename, "total_pages": total_pages})

# ─────────────────────────────────────────────
# 2. DIVIDIR PDF
# ─────────────────────────────────────────────

@app.route("/api/split", methods=["POST"])
def split_pdf():
    data = request.json
    session_id = data.get("session_id")
    pages_per_part = int(data.get("pages_per_part", 10))

    meta = load_session_meta(session_id)
    if not meta:
        return jsonify({"error": "Sesión no encontrada"}), 404

    session_path = get_session_path(session_id)
    pdf_path = session_path / "original.pdf"

    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    parts_dir = session_path / "parts"
    if parts_dir.exists():
        shutil.rmtree(str(parts_dir))
    parts_dir.mkdir()

    parts = []
    part_num = 1
    for start in range(0, total_pages, pages_per_part):
        end = min(start + pages_per_part, total_pages)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        part_filename = f"parte_{part_num:03d}.pdf"
        with open(str(parts_dir / part_filename), "wb") as f:
            writer.write(f)
        parts.append({
            "part_num": part_num,
            "filename": part_filename,
            "pages_start": start + 1,
            "pages_end": end,
            "page_count": end - start,
            "status": "pending",
            "translated_text": None
        })
        part_num += 1

    meta["parts"] = parts
    meta["pages_per_part"] = pages_per_part
    meta["status"] = "split"
    save_session_meta(session_id, meta)
    return jsonify({"session_id": session_id, "total_parts": len(parts), "parts": parts})

# ─────────────────────────────────────────────
# 3. EXTRAER TEXTO
# ─────────────────────────────────────────────

@app.route("/api/extract-text", methods=["POST"])
def extract_text():
    data = request.json
    session_id = data.get("session_id")
    part_num = int(data.get("part_num", 1))

    meta = load_session_meta(session_id)
    if not meta:
        return jsonify({"error": "Sesión no encontrada"}), 404

    session_path = get_session_path(session_id)
    part_path = session_path / "parts" / f"parte_{part_num:03d}.pdf"
    if not part_path.exists():
        return jsonify({"error": f"Parte {part_num} no encontrada"}), 404

    import pdfplumber
    text = ""
    with pdfplumber.open(str(part_path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n\n"

    return jsonify({"part_num": part_num, "text": text.strip(), "char_count": len(text)})

# ─────────────────────────────────────────────
# 4. TRADUCIR CON GOOGLE
# ─────────────────────────────────────────────

@app.route("/api/translate-google", methods=["POST"])
def translate_google():
    data = request.json
    session_id = data.get("session_id")
    part_num = int(data.get("part_num", 1))
    source_lang = data.get("source_lang", "auto")
    text = data.get("text", "")
    apply_fix = data.get("fix_dialogues", True)

    if not text.strip():
        return jsonify({"error": "No hay texto para traducir"}), 400

    try:
        from deep_translator import GoogleTranslator

        MAX_CHUNK = 4500
        chunks = []
        while len(text) > MAX_CHUNK:
            cut = text[:MAX_CHUNK].rfind('\n')
            if cut == -1:
                cut = text[:MAX_CHUNK].rfind('. ')
            if cut == -1:
                cut = MAX_CHUNK
            chunks.append(text[:cut+1])
            text = text[cut+1:]
        if text:
            chunks.append(text)

        translator = GoogleTranslator(source=source_lang, target="es")
        translated_chunks = [translator.translate(c) for c in chunks if c.strip()]
        full_translation = "\n".join(translated_chunks)

        if apply_fix:
            full_translation = post_process_spanish(full_translation)

        meta = load_session_meta(session_id)
        for part in meta["parts"]:
            if part["part_num"] == part_num:
                part["translated_text"] = full_translation
                part["status"] = "translated_google"
                break
        save_session_meta(session_id, meta)

        return jsonify({"part_num": part_num, "translated_text": full_translation, "method": "google"})
    except Exception as e:
        return jsonify({"error": f"Error en traducción: {str(e)}"}), 500

# ─────────────────────────────────────────────
# 5. MEJORAR CON IA (Gemini o Claude)
# ─────────────────────────────────────────────

@app.route("/api/translate-ai", methods=["POST"])
def translate_ai():
    data = request.json
    session_id = data.get("session_id")
    part_num = int(data.get("part_num", 1))
    text = data.get("text", "")
    is_google_result = data.get("is_google_result", False)
    apply_fix = data.get("fix_dialogues", True)
    provider = data.get("provider", "gemini")

    if not text.strip():
        return jsonify({"error": "No hay texto para procesar"}), 400

    try:
        if provider == "gemini":
            translated = _gemini(text, is_google_result)
        else:
            translated = _claude(text, is_google_result)

        if apply_fix:
            translated = post_process_spanish(translated)

        meta = load_session_meta(session_id)
        for part in meta["parts"]:
            if part["part_num"] == part_num:
                part["translated_text"] = translated
                part["status"] = f"translated_{provider}"
                break
        save_session_meta(session_id, meta)

        return jsonify({"part_num": part_num, "translated_text": translated, "method": provider})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _gemini(text, is_google_result):
    try:
        from google import genai
    except ImportError:
        raise Exception("Ejecuta: pip install google-genai")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise Exception(
            "Falta GEMINI_API_KEY en .env\n"
            "Obtén una clave GRATIS en: https://aistudio.google.com/app/apikey"
        )

    client = genai.Client(api_key=api_key)

    rules = (
        "REGLAS OBLIGATORIAS DE FORMATO ESPAÑOL:\n"
        "1. DIÁLOGOS: Usa guión largo (—) SIEMPRE, NUNCA comillas. "
        "Formato: —Texto del diálogo —dijo el personaje—. Continuación.\n"
        "2. INCISOS DEL NARRADOR: —Hola —dijo Juan—. Luego se fue. "
        "(guión largo antes y después del inciso, punto después del cierre).\n"
        "3. SIGNOS DE APERTURA: Siempre usar ¿...? y ¡...! (con apertura).\n"
        "4. MAYÚSCULAS: Después de . ? ! y ... siempre mayúscula.\n"
        "5. PUNTUACIÓN: Sin espacio antes de . , ; : ? ! — Espacio después.\n"
        "6. PÁRRAFOS: Mantén los saltos de párrafo del original. "
        "Cada diálogo de distinto personaje en párrafo aparte.\n"
        "7. NATURALIDAD: Usa expresiones naturales del español castellano, "
        "no traducciones literales. Adapta modismos e interjecciones.\n"
        "8. REGISTRO: Mantén el registro del original (formal/informal, tú/usted).\n"
        "9. NOMBRES PROPIOS: No traduzcas nombres propios de personas ni lugares ficticios.\n"
        "10. COMAS VOCATIVAS: Siempre coma antes del vocativo: —Hola, Juan.\n"
        "11. LEÍSMO/LAÍSMO: Usa los pronombres correctamente según la RAE.\n"
        "12. PUNTOS SUSPENSIVOS: Exactamente tres puntos (...), espacio después.\n"
    )

    if is_google_result:
        prompt = (
            "Eres un corrector y editor literario experto en español castellano.\n"
            "Se te proporciona una traducción automática de un libro/texto largo.\n"
            "Tu tarea es MEJORARLA para que suene como prosa literaria profesional "
            "publicada en España.\n\n"
            f"{rules}\n"
            "CORRECCIONES ADICIONALES A BUSCAR:\n"
            "- Frases que suenan a traducción literal del inglés\n"
            "- Gerundios mal usados (en español se usan menos que en inglés)\n"
            "- Voz pasiva excesiva (en español se prefiere activa o pasiva refleja)\n"
            "- Repeticiones innecesarias de sujeto pronominable\n"
            "- Falsos amigos (actually≠actualmente, etc.)\n\n"
            "Devuelve ÚNICAMENTE el texto mejorado, sin explicaciones ni comentarios.\n\n"
            f"TEXTO A MEJORAR:\n{text}"
        )
    else:
        prompt = (
            "Eres un traductor literario profesional especializado en español castellano.\n"
            "Traduce el siguiente texto manteniendo el estilo, tono y ritmo narrativo del original.\n"
            "La traducción debe leerse como una obra publicada en español, no como una traducción.\n\n"
            f"{rules}\n"
            "INSTRUCCIONES ADICIONALES:\n"
            "- Adapta modismos e interjecciones al español natural\n"
            "- Evita gerundios excesivos, voz pasiva innecesaria y calcos del inglés\n"
            "- Mantén la estructura de párrafos del original\n"
            "- Para cada diálogo de personaje distinto, usa párrafo aparte\n\n"
            "Devuelve ÚNICAMENTE la traducción, sin explicaciones ni comentarios.\n\n"
            f"TEXTO ORIGINAL:\n{text}"
        )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text


def _claude(text, is_google_result):
    try:
        import anthropic
    except ImportError:
        raise Exception("Ejecuta: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise Exception("Falta ANTHROPIC_API_KEY en .env")

    client = anthropic.Anthropic(api_key=api_key)

    rules = (
        "REGLAS: Diálogos con guión largo (—), nunca comillas. "
        "Incisos: —texto —dijo X—. Continúa. "
        "Signos de apertura obligatorios: ¿...? ¡...! "
        "Mayúscula después de . ? ! y puntos suspensivos. "
        "Coma vocativa. Sin gerundios ni pasiva innecesarios. "
        "Español castellano natural, no traducción literal."
    )

    if is_google_result:
        action = (
            f"Mejora esta traducción automática para que suene como prosa literaria "
            f"profesional en español castellano. {rules}"
        )
    else:
        action = (
            f"Traduce al español castellano como prosa literaria publicada. "
            f"Mantén estilo, tono y ritmo. {rules}"
        )
    prompt = (
        f"{action}\n"
        f"Devuelve ÚNICAMENTE el texto resultante, sin explicaciones.\n\nTEXTO:\n{text}"
    )
    msg = client.messages.create(
        model="claude-opus-4-5", max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

# ─────────────────────────────────────────────
# 5b. PIPELINE COMPLETO: Google → Gemini → Post-procesamiento
# ─────────────────────────────────────────────

@app.route("/api/translate-pipeline", methods=["POST"])
def translate_pipeline():
    """
    Pipeline completo en un solo paso:
      1. Google Translate (rápido, gratis)
      2. Gemini refina la naturalidad (gratis)
      3. Post-procesamiento lingüístico (determinístico)
    """
    data = request.json
    session_id = data.get("session_id")
    part_num = int(data.get("part_num", 1))
    source_lang = data.get("source_lang", "auto")
    text = data.get("text", "")
    skip_ai = data.get("skip_ai", False)
    provider = data.get("provider", "gemini")

    if not text.strip():
        return jsonify({"error": "No hay texto para traducir"}), 400

    steps_done = []

    try:
        # ── Paso 1: Google Translate
        from deep_translator import GoogleTranslator

        MAX_CHUNK = 4500
        chunks = []
        remaining = text
        while len(remaining) > MAX_CHUNK:
            cut = remaining[:MAX_CHUNK].rfind('\n')
            if cut == -1:
                cut = remaining[:MAX_CHUNK].rfind('. ')
            if cut == -1:
                cut = MAX_CHUNK
            chunks.append(remaining[:cut+1])
            remaining = remaining[cut+1:]
        if remaining:
            chunks.append(remaining)

        translator = GoogleTranslator(source=source_lang, target="es")
        translated_chunks = [translator.translate(c) for c in chunks if c.strip()]
        google_result = "\n".join(translated_chunks)
        steps_done.append("google")

        # ── Paso 2: Gemini/Claude refina (opcional)
        ai_result = google_result
        if not skip_ai:
            try:
                if provider == "gemini":
                    ai_result = _gemini(google_result, is_google_result=True)
                else:
                    ai_result = _claude(google_result, is_google_result=True)
                steps_done.append(provider)
            except Exception as ai_err:
                # Si falla la IA, seguimos con el resultado de Google
                print(f"Advertencia: IA ({provider}) falló, usando solo Google: {ai_err}")
                ai_result = google_result

        # ── Paso 3: Post-procesamiento lingüístico
        final = post_process_spanish(ai_result)
        steps_done.append("postprocess")

        # Guardar
        meta = load_session_meta(session_id)
        method = "+".join(steps_done)
        for part in meta["parts"]:
            if part["part_num"] == part_num:
                part["translated_text"] = final
                part["status"] = f"translated_pipeline"
                break
        save_session_meta(session_id, meta)

        return jsonify({
            "part_num": part_num,
            "translated_text": final,
            "method": method,
            "steps": steps_done,
        })

    except Exception as e:
        return jsonify({"error": f"Error en pipeline: {str(e)}"}), 500

# ─────────────────────────────────────────────
# 6. GUARDAR TRADUCCIÓN MANUAL
# ─────────────────────────────────────────────

@app.route("/api/save-translation", methods=["POST"])
def save_translation():
    data = request.json
    session_id = data.get("session_id")
    part_num = int(data.get("part_num", 1))
    translated_text = data.get("translated_text", "")
    apply_fix = data.get("fix_dialogues", False)

    meta = load_session_meta(session_id)
    if not meta:
        return jsonify({"error": "Sesión no encontrada"}), 404

    if apply_fix:
        translated_text = post_process_spanish(translated_text)

    for part in meta["parts"]:
        if part["part_num"] == part_num:
            part["translated_text"] = translated_text
            part["status"] = "translated_manual"
            break

    save_session_meta(session_id, meta)
    return jsonify({"success": True, "part_num": part_num, "translated_text": translated_text})

# ─────────────────────────────────────────────
# 7. GENERAR PDF FINAL (con imágenes)
# ─────────────────────────────────────────────

@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf():
    data = request.json
    session_id = data.get("session_id")
    selected_parts = data.get("selected_parts", [])
    include_images = data.get("include_images", True)

    meta = load_session_meta(session_id)
    if not meta:
        return jsonify({"error": "Sesión no encontrada"}), 404

    parts_to_include = meta["parts"]
    if selected_parts:
        parts_to_include = [p for p in parts_to_include if p["part_num"] in selected_parts]

    for part in parts_to_include:
        if not part.get("translated_text"):
            return jsonify({
                "error": f"La parte {part['part_num']} aún no tiene traducción."
            }), 400

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                        Spacer, PageBreak, Image as RLImage)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors

        session_path = get_session_path(session_id)
        output_filename = f"traduccion_{session_id[:8]}.pdf"
        output_path = session_path / output_filename

        PAGE_W, PAGE_H = A4
        MARGIN = 2.5 * cm
        CONTENT_W = PAGE_W - 2 * MARGIN

        doc = SimpleDocTemplate(
            str(output_path), pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=MARGIN, bottomMargin=MARGIN
        )

        styles = getSampleStyleSheet()
        style_title = ParagraphStyle(
            "PartTitle", parent=styles["Heading2"],
            textColor=colors.HexColor("#2563eb"),
            spaceAfter=12, spaceBefore=20,
        )
        style_body = ParagraphStyle(
            "Body", parent=styles["Normal"],
            fontSize=11, leading=17, spaceAfter=6,
        )
        style_dialog = ParagraphStyle(
            "Dialog", parent=styles["Normal"],
            fontSize=11, leading=17, spaceAfter=4, leftIndent=12,
        )
        style_cover = ParagraphStyle(
            "Cover", parent=styles["Title"],
            fontSize=24, textColor=colors.HexColor("#1e40af"), spaceAfter=20,
        )

        story = []

        # ── Portada
        original_name = meta.get("original_filename", "documento.pdf")
        story.append(Spacer(1, 3*cm))
        story.append(Paragraph("Traducción al Español", style_cover))
        story.append(Paragraph(f"Documento original: {original_name}", style_body))
        story.append(Paragraph(f"Partes incluidas: {len(parts_to_include)}", style_body))
        story.append(PageBreak())

        # ── Extraer imágenes del PDF original
        all_images = []
        if include_images:
            original_pdf = session_path / "original.pdf"
            imgs_dir = session_path / "images"
            imgs_dir.mkdir(exist_ok=True)
            if original_pdf.exists():
                all_images = extract_images_from_pdf(original_pdf, imgs_dir)

        # ── Contenido
        for part in parts_to_include:
            story.append(Paragraph(
                f"Parte {part['part_num']} — Páginas {part['pages_start']} a {part['pages_end']}",
                style_title
            ))

            # Imágenes de las páginas de esta parte
            if include_images and all_images:
                p0 = part["pages_start"] - 1
                p1 = part["pages_end"] - 1
                part_imgs = [img for img in all_images if p0 <= img["page"] <= p1]
                for img_info in part_imgs[:8]:
                    try:
                        ip = Path(img_info["path"])
                        if ip.exists():
                            w_px = img_info["width_px"]
                            h_px = img_info["height_px"]
                            # Escalar manteniendo proporción, máx. CONTENT_W
                            scale = min(CONTENT_W / w_px, (12*cm) / h_px, 1.0)
                            rw = w_px * scale
                            rh = h_px * scale
                            story.append(RLImage(str(ip), width=rw, height=rh))
                            story.append(Spacer(1, 8))
                    except Exception as ie:
                        print(f"Imagen omitida en PDF final: {ie}")

            # Texto traducido
            for para in part["translated_text"].split('\n'):
                para = para.strip()
                if para:
                    is_dialog = para.startswith('—')
                    safe = para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    try:
                        story.append(Paragraph(safe, style_dialog if is_dialog else style_body))
                    except Exception:
                        story.append(Paragraph(safe[:500], style_body))
                else:
                    story.append(Spacer(1, 5))

            story.append(PageBreak())

        doc.build(story)

        return jsonify({
            "success": True,
            "filename": output_filename,
            "download_url": f"/api/download/{session_id}/{output_filename}"
        })

    except Exception as e:
        return jsonify({"error": f"Error generando PDF: {str(e)}"}), 500

# ─────────────────────────────────────────────
# 8-10. DESCARGAR / SESIÓN / PARTE
# ─────────────────────────────────────────────

@app.route("/api/download/<session_id>/<filename>")
def download_file(session_id, filename):
    fp = get_session_path(session_id) / filename
    if not fp.exists():
        return jsonify({"error": "Archivo no encontrado"}), 404
    return send_file(str(fp), as_attachment=True, download_name=filename)

@app.route("/api/session/<session_id>")
def get_session(session_id):
    meta = load_session_meta(session_id)
    if not meta:
        return jsonify({"error": "Sesión no encontrada"}), 404
    return jsonify(meta)

@app.route("/api/download-part/<session_id>/<int:part_num>")
def download_part(session_id, part_num):
    fp = get_session_path(session_id) / "parts" / f"parte_{part_num:03d}.pdf"
    if not fp.exists():
        return jsonify({"error": "Parte no encontrada"}), 404
    return send_file(str(fp), as_attachment=True, download_name=fp.name)

# ─────────────────────────────────────────────
# 11. ENDPOINT: CORREGIR TEXTO (pipeline completo español)
# ─────────────────────────────────────────────

@app.route("/api/fix-dialogues", methods=["POST"])
def fix_dialogues_api():
    data = request.json
    fixed = post_process_spanish(data.get("text", ""))
    return jsonify({"fixed_text": fixed})

# ─────────────────────────────────────────────
# SERVIR FRONTEND DESDE FLASK
# ─────────────────────────────────────────────

FRONTEND_DIR = BASE_DIR / "frontend"

@app.route("/")
def serve_frontend():
    return send_file(str(FRONTEND_DIR / "index.html"))

@app.route("/<path:filename>")
def serve_static(filename):
    fp = FRONTEND_DIR / filename
    if fp.exists() and fp.is_file():
        return send_file(str(fp))
    return jsonify({"error": "No encontrado"}), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n🚀 PDF Translator v2 — http://localhost:{port}")
    print("   ✅ Abre tu navegador en: http://localhost:{port}".format(port=port))
    print("   ✅ Gemini Flash (gratis) como motor de IA principal")
    print("   ✅ Pipeline: Google → Gemini → Post-procesamiento")
    print("   ✅ Diálogos: comillas → guión largo automático")
    print("   ✅ Imágenes del PDF original preservadas\n")
    app.run(debug=True, port=port)
