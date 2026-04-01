"""
Linguistic post-processing pipeline for translated Spanish text.

Pipeline steps (applied per paragraph):
  1. Normalize — whitespace, quotes, punctuation, chunking artifacts
  2. Hunspell — basic Spanish spellcheck
  3. LanguageTool — grammar and punctuation correction
  4. Linguistic rules (spaCy + regex) — fix literal translations, collocations
  5. Optional AI refinement — only if enabled and quality is below threshold

Thread-safe: all functions are pure (no shared mutable state).
Fail-safe: each step catches its own errors and falls through gracefully.
"""

import re
import os
import threading
import hashlib

# ─────────────────────────────────────────────
# Lazy-loaded singletons (thread-safe)
# ─────────────────────────────────────────────

_hunspell_lock = threading.Lock()
_hunspell_instance = None  # None=not tried, False=unavailable, HunSpell=ready

_spacy_lock = threading.Lock()
_spacy_nlp = None  # None=not tried, False=unavailable, Language=ready

# ─────────────────────────────────────────────
# LanguageTool response cache (LRU-style, thread-safe)
# ─────────────────────────────────────────────

_lt_cache_lock = threading.Lock()
_lt_cache = {}       # hash(text) → corrected_text
_LT_CACHE_MAX = 2000  # max entries before eviction

# Bad collocations: literal English→Spanish translations → natural equivalents
BAD_COLLOCATIONS = [
    # (regex pattern, replacement)
    (r'\bhace sentido\b', 'tiene sentido'),
    (r'\bhacía sentido\b', 'tenía sentido'),
    (r'\btomar lugar\b', 'tener lugar'),
    (r'\btomó lugar\b', 'tuvo lugar'),
    (r'\btomar una decisión\b', 'tomar una decisión'),
    (r'\bhacer una decisión\b', 'tomar una decisión'),
    (r'\bhizo una decisión\b', 'tomó una decisión'),
    (r'\bpagar atención\b', 'prestar atención'),
    (r'\bpagó atención\b', 'prestó atención'),
    (r'\btomar ventaja\b', 'aprovecharse'),
    (r'\btomó ventaja\b', 'se aprovechó'),
    (r'\ben orden de\b', 'para'),
    (r'\ben adición a\b', 'además de'),
    (r'\ben adición\b', 'además'),
    (r'\bal final del día\b', 'en definitiva'),
    (r'\ben este punto en el tiempo\b', 'en este momento'),
    (r'\bde vuelta en el día\b', 'en aquella época'),
    (r'\bsacudió su cabeza\b', 'negó con la cabeza'),
    (r'\bsacudió la cabeza\b', 'negó con la cabeza'),
    (r'\basintió con su cabeza\b', 'asintió'),
    (r'\basintió con la cabeza\b', 'asintió'),
    (r'\brodó sus ojos\b', 'puso los ojos en blanco'),
    (r'\brodó los ojos\b', 'puso los ojos en blanco'),
    (r'\bhizo su camino\b', 'se dirigió'),
    (r'\bhicieron su camino\b', 'se dirigieron'),
    (r'\bsus ojos se ensancharon\b', 'abrió los ojos de par en par'),
    (r'\bdejó ir\b', 'soltó'),
    (r'\bdejó salir un suspiro\b', 'exhaló un suspiro'),
    (r'\bdejó salir una risa\b', 'soltó una risa'),
    (r'\bdejó salir un grito\b', 'lanzó un grito'),
    (r'\btodo de un repentino\b', 'de repente'),
    (r'\bde un repentino\b', 'de repente'),
    (r'\bencogió sus hombros\b', 'se encogió de hombros'),
    (r'\balzó sus cejas\b', 'enarcó las cejas'),
    (r'\bcruzó sus brazos\b', 'se cruzó de brazos'),
    # Redundant possessives (English literal)
    (r'\bse lavó sus\b', 'se lavó las'),
    (r'\bse tocó su\b', 'se tocó la'),
    (r'\bse frotó sus\b', 'se frotó las'),
    (r'\bse mordió su\b', 'se mordió el'),
    (r'\babrió sus ojos\b', 'abrió los ojos'),
    (r'\bcerró sus ojos\b', 'cerró los ojos'),
    (r'\babrió su boca\b', 'abrió la boca'),
    (r'\bcerró su boca\b', 'cerró la boca'),
    (r'\blevantó su mano\b', 'levantó la mano'),
    (r'\blevantó sus manos\b', 'levantó las manos'),
    (r'\bmetió sus manos\b', 'metió las manos'),
    (r'\bmetió su mano\b', 'metió la mano'),
    # Preposition fixes
    (r'\bconsistir de\b', 'consistir en'),
    (r'\bpensar sobre\b', 'pensar en'),
    (r'\bsoñar sobre\b', 'soñar con'),
    (r'\bsoñó sobre\b', 'soñó con'),
    (r'\bpreocuparse sobre\b', 'preocuparse por'),
    (r'\bse preocupó sobre\b', 'se preocupó por'),
    (r'\binsistir sobre\b', 'insistir en'),
    (r'\binsistió sobre\b', 'insistió en'),
    (r'\bdiferente a\b', 'diferente de'),
    (r'\bdiferentes a\b', 'diferentes de'),
    # Idioms
    (r'\bllover gatos y perros\b', 'llover a cántaros'),
    (r'\bllovía gatos y perros\b', 'llovía a cántaros'),
    (r'\bun pedazo de pastel\b', 'pan comido'),
    (r'\bel elefante en la habitación\b', 'el problema evidente'),
    (r'\bbajo el clima\b', 'indispuesto'),
    (r'\bcuesta un brazo y una pierna\b', 'cuesta un ojo de la cara'),
    (r'\bcostó un brazo y una pierna\b', 'costó un ojo de la cara'),
]

# Sentence patterns that indicate unnatural literal translation (for spaCy step)
LITERAL_TRANSLATION_PATTERNS = [
    # "Estar + gerundio" overuse (English progressive)
    (r'\bestaba\s+siendo\b', 'era'),
    (r'\bestaban\s+siendo\b', 'eran'),
    # "Es/Son + participio" without agent → pasiva refleja
    (r'\bes considerado\b', 'se considera'),
    (r'\bson considerados\b', 'se consideran'),
    (r'\bes llamad[oa]\b', 'se llama'),
    (r'\bson llamad[oa]s\b', 'se llaman'),
    (r'\bes dicho que\b', 'se dice que'),
    (r'\bes sabido que\b', 'se sabe que'),
    (r'\bes esperado que\b', 'se espera que'),
    # "Siendo que" → "dado que"
    (r'\bsiendo que\b', 'dado que'),
    # "Habiendo dicho eso" → "dicho esto"
    (r'\bhabiendo dicho eso\b', 'dicho esto'),
]


class _SpyllsWrapper:
    """Wrapper around spylls.hunspell to match pyhunspell's .spell()/.suggest() API."""
    def __init__(self, dictionary):
        self._dict = dictionary

    def spell(self, word):
        return self._dict.lookup(word)

    def suggest(self, word):
        return list(self._dict.suggest(word))


def _get_hunspell():
    """Lazily load Hunspell with Spanish dictionary. Thread-safe.
    Tries pyhunspell first, then falls back to spylls (pure Python)."""
    global _hunspell_instance
    if _hunspell_instance is not None:
        return _hunspell_instance if _hunspell_instance is not False else None
    with _hunspell_lock:
        if _hunspell_instance is not None:
            return _hunspell_instance if _hunspell_instance is not False else None

        backend_dir = os.path.dirname(os.path.abspath(__file__))
        dict_paths = [
            (os.path.join(backend_dir, "dicts", "es_ES.dic"),
             os.path.join(backend_dir, "dicts", "es_ES.aff")),
            ("/usr/share/hunspell/es_ES.dic", "/usr/share/hunspell/es_ES.aff"),
            ("/usr/share/myspell/dicts/es_ES.dic", "/usr/share/myspell/dicts/es_ES.aff"),
        ]

        # 1) Try native pyhunspell
        try:
            import hunspell as _hunspell_mod
            for dic_path, aff_path in dict_paths:
                if os.path.exists(dic_path) and os.path.exists(aff_path):
                    _hunspell_instance = _hunspell_mod.HunSpell(dic_path, aff_path)
                    print("[postprocess] Hunspell (native) loaded")
                    return _hunspell_instance
        except ImportError:
            pass
        except Exception:
            pass

        # 2) Fallback: spylls (pure Python Hunspell)
        try:
            from spylls.hunspell import Dictionary
            for dic_path, aff_path in dict_paths:
                if os.path.exists(dic_path) and os.path.exists(aff_path):
                    base = dic_path.rsplit('.', 1)[0]  # path without extension
                    _hunspell_instance = _SpyllsWrapper(Dictionary.from_files(base))
                    print("[postprocess] Hunspell (spylls) loaded")
                    return _hunspell_instance
        except ImportError:
            pass
        except Exception as e:
            print(f"[postprocess] spylls init error: {e}")

        print("[postprocess] No spellcheck backend available, skipping")
        _hunspell_instance = False
        return None


def _get_spacy_nlp():
    """Lazily load spaCy with Spanish model. Thread-safe."""
    global _spacy_nlp
    if _spacy_nlp is not None:
        return _spacy_nlp if _spacy_nlp is not False else None
    with _spacy_lock:
        if _spacy_nlp is not None:
            return _spacy_nlp if _spacy_nlp is not False else None
        try:
            import spacy
            try:
                _spacy_nlp = spacy.load("es_core_news_sm")
            except OSError:
                print("[postprocess] Downloading spaCy Spanish model...")
                from spacy.cli import download
                download("es_core_news_sm")
                _spacy_nlp = spacy.load("es_core_news_sm")
            return _spacy_nlp
        except ImportError:
            print("[postprocess] spaCy not installed (pip install spacy), skipping linguistic analysis")
            _spacy_nlp = False
            return None
        except Exception as e:
            print(f"[postprocess] spaCy init error: {e}")
            _spacy_nlp = False
            return None


# ═════════════════════════════════════════════
# STEP 1: NORMALIZE
# ═════════════════════════════════════════════

def step_normalize(text):
    """Fix whitespace, quotes, punctuation, and chunking artifacts."""
    if not text or not text.strip():
        return text

    # --- Whitespace ---
    text = text.replace('\t', ' ')
    text = re.sub(r'[^\S\n]+', ' ', text)
    text = re.sub(r' +\n', '\n', text)
    text = re.sub(r'\n +(?!—)', '\n', text)
    text = re.sub(r'\n{4,}', '\n\n\n', text)

    # --- Normalize quotes to standard forms ---
    # Curly/smart quotes → straight (then dialogue rules will convert to em-dash)
    text = text.replace('\u201c', '"').replace('\u201d', '"')  # " " → "
    text = text.replace('\u2018', "'").replace('\u2019', "'")  # ' ' → '
    text = text.replace('\u00ab', '«').replace('\u00bb', '»')  # keep guillemets

    # --- Remove chunking artifacts ---
    # Repeated sentence fragments at chunk boundaries
    text = re.sub(r'(\.\s*)\1{2,}', r'\1', text)
    # Orphaned sentence starters from chunk splits
    text = re.sub(r'\n\s*\.\s*\n', '\n', text)
    # Multiple consecutive identical lines (dedup)
    lines = text.split('\n')
    deduped = [lines[0]] if lines else []
    for i in range(1, len(lines)):
        if lines[i].strip() and lines[i].strip() == lines[i - 1].strip():
            continue
        deduped.append(lines[i])
    text = '\n'.join(deduped)

    # --- Punctuation normalization ---
    # Fix spaces before punctuation
    text = re.sub(r' +([.,;:?!)\]»])', r'\1', text)
    # Fix spaces after opening marks
    text = re.sub(r'([([«¿¡]) +', r'\1', text)
    # Ensure space after punctuation before words
    text = re.sub(r'([.,;:?!])([A-Za-záéíóúñÁÉÍÓÚÑ])', r'\1 \2', text)
    # Fix ellipsis
    text = re.sub(r'(?<!\.)\.{2}(?!\.)', '...', text)
    text = re.sub(r'\.{4,}', '...', text)
    text = re.sub(r'(\.\.\.)([A-Za-záéíóúñÁÉÍÓÚÑ])', r'\1 \2', text)
    # Fix double punctuation
    text = re.sub(r'([.])\1(?!\.)', r'\1', text)
    text = re.sub(r',,+', ',', text)
    text = re.sub(r';;+', ';', text)

    # --- Capitalize after sentence-ending punctuation ---
    text = re.sub(r'([.?!]) (\w)', lambda m: m.group(1) + ' ' + m.group(2).upper(), text)
    text = re.sub(r'(\.{3}) (\w)', lambda m: m.group(1) + ' ' + m.group(2).upper(), text)

    # --- Opening marks (¿ ¡) ---
    text = _fix_opening_marks(text)

    # --- Ordinals ---
    text = re.sub(r'\b(\d+)(?:st|nd|rd|th)\b', r'\1.º', text)

    return text.strip()


def _fix_opening_marks(text):
    """Ensure ¿...? and ¡...! always have opening marks."""
    lines = text.split('\n')
    result = []
    for line in lines:
        line = re.sub(
            r'(?<![¿\w])([A-Za-zÁÉÍÓÚÑáéíóúñ¿][^.!?¡¿]*?\?)',
            lambda m: m.group(1) if '¿' in m.group(1) else '¿' + m.group(1),
            line
        )
        line = re.sub(
            r'(?<![¡\w])([A-Za-zÁÉÍÓÚÑáéíóúñ¡][^.!?¡¿]*?!)',
            lambda m: m.group(1) if '¡' in m.group(1) else '¡' + m.group(1),
            line
        )
        result.append(line)
    return '\n'.join(result)


# ═════════════════════════════════════════════
# STEP 2: HUNSPELL SPELLCHECK
# ═════════════════════════════════════════════

# Words to never "correct" (proper nouns, abbreviations, etc.)
_SPELLCHECK_SKIP = re.compile(
    r'^[A-ZÁÉÍÓÚÑ]{2,}$'       # ALL CAPS words
    r'|^\d'                     # starts with digit
    r'|^[—\-\*\#]'             # starts with symbol
    r'|^https?://'              # URLs
    r'|@'                       # emails
)


def step_hunspell(text):
    """Correct basic spelling errors using Hunspell Spanish dictionary."""
    hs = _get_hunspell()
    if hs is None:
        return text

    is_spylls = isinstance(hs, _SpyllsWrapper)
    MAX_WORDS = 500  # limit to prevent hanging on large texts
    words_checked = 0

    # Process word by word, preserving structure
    def _correct_word(word):
        nonlocal words_checked
        # Skip short words, punctuation, numbers, proper nouns at sentence start
        if len(word) < 3:
            return word
        if _SPELLCHECK_SKIP.search(word):
            return word
        # Skip words with special chars
        clean = re.sub(r'[.,;:?!¿¡»«\'"()\[\]—]', '', word)
        if not clean or len(clean) < 3:
            return word

        words_checked += 1
        if words_checked > MAX_WORDS:
            return word  # stop checking after limit

        try:
            if hs.spell(clean):
                return word  # word is correct
            # spylls suggest() is extremely slow — skip it for spylls backend
            if is_spylls:
                return word
            suggestions = hs.suggest(clean)
            if suggestions:
                # Use first suggestion, preserving surrounding punctuation
                return word.replace(clean, suggestions[0])
        except Exception:
            pass
        return word

    # Split into lines, then tokens
    lines = text.split('\n')
    corrected_lines = []
    for line in lines:
        tokens = line.split(' ')
        corrected_tokens = [_correct_word(t) for t in tokens]
        corrected_lines.append(' '.join(corrected_tokens))

    return '\n'.join(corrected_lines)


# ═════════════════════════════════════════════
# STEP 3: LANGUAGETOOL GRAMMAR CORRECTION
# ═════════════════════════════════════════════

def step_languagetool(text):
    """Apply grammar and punctuation corrections via LanguageTool API (Spanish).
    Results are cached by content hash to avoid redundant API calls."""
    import requests as _requests

    if not text.strip():
        return text

    # Check cache first
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    with _lt_cache_lock:
        if text_hash in _lt_cache:
            return _lt_cache[text_hash]

    # Split into chunks (API limit ~20KB)
    MAX_CHUNK = 15000
    paragraphs = text.split('\n')
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 1 > MAX_CHUNK and current:
            chunks.append(current)
            current = p
        else:
            current = current + '\n' + p if current else p
    if current:
        chunks.append(current)

    corrected_chunks = []
    for chunk in chunks:
        corrected_chunks.append(_languagetool_check(chunk, _requests))

    result = '\n'.join(corrected_chunks)

    # Store in cache
    with _lt_cache_lock:
        if len(_lt_cache) >= _LT_CACHE_MAX:
            # Evict oldest half
            keys = list(_lt_cache.keys())
            for k in keys[:len(keys) // 2]:
                del _lt_cache[k]
        _lt_cache[text_hash] = result

    return result


def _languagetool_check(chunk, _requests):
    """Send a single chunk to LanguageTool API and apply safe corrections."""
    try:
        r = _requests.post(
            'https://api.languagetool.org/v2/check',
            data={'text': chunk, 'language': 'es'},
            timeout=10,
        )
        if r.status_code != 200:
            return chunk

        matches = r.json().get('matches', [])
        safe_matches = []
        for m in matches:
            if not m.get('replacements'):
                continue
            original_word = chunk[m['offset']:m['offset'] + m['length']]
            # Skip proper nouns (capitalized, not at sentence start)
            if (original_word and original_word[0].isupper()
                    and m['offset'] > 0
                    and chunk[m['offset'] - 1] not in '.?!¿¡\n'
                    and m.get('rule', {}).get('id') == 'MORFOLOGIK_RULE_ES'):
                continue
            safe_matches.append(m)

        result = chunk
        for m in reversed(safe_matches):
            if m.get('replacements'):
                start = m['offset']
                end = start + m['length']
                result = result[:start] + m['replacements'][0]['value'] + result[end:]
        return result
    except Exception as e:
        print(f"[postprocess] LanguageTool error: {e}")
        return chunk


def step_languagetool_batch(texts):
    """Check multiple texts via LanguageTool, batching into fewer API calls.
    Returns list of corrected texts in the same order.

    Strategy: concatenate paragraphs separated by double-newline into chunks
    up to 15 KB, send one API call per chunk, then split results back.
    """
    import requests as _requests

    if not texts:
        return []

    SEPARATOR = '\n\n¶¶¶\n\n'  # unique separator unlikely in real text
    MAX_CHUNK = 15000
    results = [''] * len(texts)

    # Check cache and split into cached vs uncached
    uncached = []  # (original_index, text)
    for i, t in enumerate(texts):
        if not t or not t.strip():
            results[i] = t
            continue
        text_hash = hashlib.md5(t.encode('utf-8')).hexdigest()
        with _lt_cache_lock:
            if text_hash in _lt_cache:
                results[i] = _lt_cache[text_hash]
                continue
        uncached.append((i, t))

    if not uncached:
        return results

    # Build mega-chunks from uncached paragraphs
    mega_chunks = []  # list of (chunk_text, [(original_index, paragraph_text), ...])
    current_chunk = ""
    current_items = []
    for orig_idx, t in uncached:
        candidate = (current_chunk + SEPARATOR + t) if current_chunk else t
        if len(candidate.encode('utf-8')) > MAX_CHUNK and current_chunk:
            mega_chunks.append((current_chunk, list(current_items)))
            current_chunk = t
            current_items = [(orig_idx, t)]
        else:
            current_chunk = candidate
            current_items.append((orig_idx, t))
    if current_chunk:
        mega_chunks.append((current_chunk, list(current_items)))

    # Send one API call per mega-chunk
    import time as _time
    for chunk_idx, (mega_text, items) in enumerate(mega_chunks):
        if chunk_idx > 0:
            _time.sleep(0.5)  # rate-limit: short pause between API calls
        corrected_mega = _languagetool_check(mega_text, _requests)

        # Split corrected mega-chunk back into individual paragraphs
        parts = corrected_mega.split(SEPARATOR)
        for j, (orig_idx, original_text) in enumerate(items):
            corrected = parts[j].strip() if j < len(parts) else original_text
            results[orig_idx] = corrected
            # Cache the result
            text_hash = hashlib.md5(original_text.encode('utf-8')).hexdigest()
            with _lt_cache_lock:
                if len(_lt_cache) >= _LT_CACHE_MAX:
                    keys = list(_lt_cache.keys())
                    for k in keys[:len(keys) // 2]:
                        del _lt_cache[k]
                _lt_cache[text_hash] = corrected

    return results


# ═════════════════════════════════════════════
# STEP 4: LINGUISTIC IMPROVEMENT (spaCy + rules)
# ═════════════════════════════════════════════

def step_linguistic(text):
    """
    Detect and fix unnatural literal translations using:
    - Regex-based collocation fixes (always applied)
    - spaCy NLP analysis for deeper patterns (if available)
    """
    if not text or not text.strip():
        return text

    # --- Phase A: Regex-based collocation and pattern fixes (always runs) ---
    for pattern, replacement in BAD_COLLOCATIONS:
        try:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        except Exception:
            continue

    for pattern, replacement in LITERAL_TRANSLATION_PATTERNS:
        try:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        except Exception:
            continue

    # --- Phase B: Apply spanish_rules module (full rule engine) ---
    try:
        try:
            from spanish_rules import apply_spanish_rules
        except ImportError:
            from backend.spanish_rules import apply_spanish_rules
        text = apply_spanish_rules(text)
    except Exception as e:
        print(f"[postprocess] spanish_rules error: {e}")

    # --- Phase C: spaCy-based analysis (if available) ---
    nlp = _get_spacy_nlp()
    if nlp is not None:
        text = _spacy_improve(nlp, text)

    return text


def _spacy_improve(nlp, text):
    """
    Use spaCy NLP to detect and fix unnatural patterns that regex can't catch.
    Parses the text with nlp() and delegates to _spacy_improve_from_doc.
    """
    try:
        MAX_CHARS = 50000
        if len(text) > MAX_CHARS:
            mid = text[:MAX_CHARS].rfind('\n')
            if mid == -1:
                mid = MAX_CHARS
            return _spacy_improve(nlp, text[:mid]) + '\n' + _spacy_improve(nlp, text[mid + 1:])

        doc = nlp(text)
        return _spacy_improve_from_doc(doc)
    except Exception as e:
        print(f"[postprocess] spaCy analysis error: {e}")
        return text


def _spacy_improve_from_doc(doc):
    """
    Apply spaCy-based NLP rules on a pre-parsed Doc object.
    Used by both single-paragraph and batch pipelines.

    Rules applied (in order):
      R1. Redundant subject pronouns (pro-drop) — remove 2nd+ subject pronoun
      R2. Possessive → article for body parts / clothing
      R3. Excessive "que que" chains — simplify nested subordination
      R4. Consecutive repeated sentence starters — vary openers
      R5. Adjective before noun (English order) → noun + adj (Spanish order)
      R6. "Estar + gerund" in past → simple past tense
      R7. Passive "ser + participle" without agent → pasiva refleja
      R8. Dequeísmo / queísmo detection
    """
    try:
        text = doc.text
        replacements = []  # list of (start, end, new_text)

        # ── Gather sentences ──
        sents = list(doc.sents)

        for sent in sents:
            tokens = list(sent)

            # ── R1: Redundant subject pronouns (pro-drop) ──
            _rule_prodrop(sent, tokens, replacements)

            # ── R2: Possessive → article for body/clothing ──
            _rule_possessive_to_article(sent, tokens, replacements)

            # ── R5: Adjective before noun (English order) ──
            _rule_adjective_order(sent, tokens, replacements)

            # ── R6: "Estar + gerund" → simple tense ──
            _rule_estar_gerund(sent, tokens, replacements)

            # ── R7: Passive "ser + participle" without agent → pasiva refleja ──
            _rule_passive_to_refleja(sent, tokens, replacements)

        # ── R3: Excessive "que" chains ──
        _rule_que_chains(doc, replacements)

        # ── R4: Consecutive repeated sentence starters ──
        text = _rule_varied_starters(sents, text)

        # ── R8: Dequeísmo ──
        _rule_dequeismo(doc, replacements)

        # Apply all character-offset replacements in reverse order
        # Deduplicate overlapping ranges (keep first encountered)
        replacements.sort(key=lambda x: x[0], reverse=True)
        used_ranges = []
        result = text
        for start, end, repl in replacements:
            # Skip if overlaps with an already-applied replacement
            if any(s < end and start < e for s, e in used_ranges):
                continue
            result = result[:start] + repl + result[end:]
            used_ranges.append((start, end))

        return result
    except Exception as e:
        print(f"[postprocess] spaCy analysis error: {e}")
        return text


# ─── Body-part / clothing nouns (for possessive→article rule) ───
_BODY_PARTS = {
    "mano", "manos", "pie", "pies", "cabeza", "ojos", "ojo", "boca",
    "nariz", "brazo", "brazos", "pierna", "piernas", "dedo", "dedos",
    "pelo", "cabello", "cuello", "espalda", "hombro", "hombros",
    "rodilla", "rodillas", "pecho", "cara", "frente", "labios", "labio",
    "ceja", "cejas", "mejilla", "mejillas", "barbilla", "mentón",
    "muñeca", "codo", "tobillo", "cintura", "cadera",
    # Clothing
    "camisa", "chaqueta", "abrigo", "sombrero", "gorra", "bufanda",
    "corbata", "guantes", "zapatos", "botas", "gafas",
}

# ─── Adjectives that sound unnatural BEFORE a noun in Spanish ───
_COLOR_ADJS = {
    "rojo", "roja", "rojos", "rojas", "azul", "azules",
    "verde", "verdes", "amarillo", "amarilla", "amarillos", "amarillas",
    "blanco", "blanca", "blancos", "blancas", "negro", "negra", "negros", "negras",
    "gris", "grises", "naranja", "naranjas", "morado", "morada",
    "rosado", "rosada", "marrón", "dorado", "dorada", "plateado", "plateada",
}
_PHYSICAL_ADJS = {
    "alto", "alta", "altos", "altas", "bajo", "baja", "largo", "larga",
    "corto", "corta", "ancho", "ancha", "estrecho", "estrecha",
    "gordo", "gorda", "delgado", "delgada", "redondo", "redonda",
    "cuadrado", "cuadrada", "pesado", "pesada", "ligero", "ligera",
    "grueso", "gruesa", "fino", "fina", "duro", "dura", "blando", "blanda",
    "húmedo", "húmeda", "seco", "seca", "caliente", "frío", "fría",
}
_POSTPOSITIVE_ADJS = _COLOR_ADJS | _PHYSICAL_ADJS

# ─── Verbs that take "de que" correctly (not dequeísmo) ───
_VERBS_DE_QUE = {
    "acordarse", "acordar", "alegrarse", "arrepentirse", "asegurarse",
    "convencer", "darse cuenta", "olvidarse", "tratar", "quejarse",
    "enterarse", "preocuparse", "depender", "encargarse",
}

# ─── Safe gerund → imperfect mappings ───
_GERUND_MAP = {
    "caminando": "caminaba", "hablando": "hablaba", "mirando": "miraba",
    "pensando": "pensaba", "llorando": "lloraba", "gritando": "gritaba",
    "esperando": "esperaba", "buscando": "buscaba", "intentando": "intentaba",
    "tratando": "trataba", "trabajando": "trabajaba", "jugando": "jugaba",
    "escuchando": "escuchaba", "observando": "observaba", "corriendo": "corría",
    "leyendo": "leía", "escribiendo": "escribía", "durmiendo": "dormía",
    "sonriendo": "sonreía", "comiendo": "comía", "bebiendo": "bebía",
    "temblando": "temblaba", "respirando": "respiraba", "susurrando": "susurraba",
    "cantando": "cantaba", "bailando": "bailaba", "rezando": "rezaba",
    "conduciendo": "conducía", "siguiendo": "seguía", "viviendo": "vivía",
    "sintiendo": "sentía", "subiendo": "subía", "bajando": "bajaba",
}


def _rule_prodrop(sent, tokens, replacements):
    """R1: Remove redundant subject pronouns (Spanish is pro-drop)."""
    subject_pronouns = [t for t in tokens
                        if t.dep_ == "nsubj" and t.pos_ == "PRON"
                        and t.text.lower() in ("él", "ella", "yo", "tú",
                                                "nosotros", "nosotras",
                                                "ellos", "ellas")]
    if len(subject_pronouns) >= 2:
        # Keep the first, remove the rest (with trailing space)
        for pron in subject_pronouns[1:]:
            start = pron.idx
            end = start + len(pron.text)
            # Consume trailing whitespace
            while end < sent.end_char and sent.text[end - sent.start_char:end - sent.start_char + 1] == ' ':
                end += 1
            replacements.append((start, end, ''))


def _rule_possessive_to_article(sent, tokens, replacements):
    """R2: Replace possessive + body part with article (su mano → la mano)."""
    POSS_MAP = {
        "su": {"m_s": "el", "f_s": "la", "m_p": "los", "f_p": "las"},
        "sus": {"m_s": "los", "f_s": "las", "m_p": "los", "f_p": "las"},
        "mi": {"m_s": "el", "f_s": "la", "m_p": "los", "f_p": "las"},
        "mis": {"m_s": "los", "f_s": "las", "m_p": "los", "f_p": "las"},
        "tu": {"m_s": "el", "f_s": "la", "m_p": "los", "f_p": "las"},
        "tus": {"m_s": "los", "f_s": "las", "m_p": "los", "f_p": "las"},
    }
    for i, tok in enumerate(tokens):
        if tok.text.lower() in POSS_MAP and i + 1 < len(tokens):
            next_tok = tokens[i + 1]
            if next_tok.text.lower() in _BODY_PARTS:
                morph = next_tok.morph
                gender = "f" if "Fem" in morph.get("Gender", []) else "m"
                number = "p" if "Plur" in morph.get("Number", []) else "s"
                key = f"{gender}_{number}"
                # If spaCy can't determine, guess from word ending
                if key == "m_s":
                    w = next_tok.text.lower()
                    if w.endswith("a") or w.endswith("as"):
                        key = "f_p" if w.endswith("as") else "f_s"
                    elif w.endswith("s") or w.endswith("es"):
                        key = "m_p"
                article = POSS_MAP[tok.text.lower()].get(key, "la")
                # Check verb context — only replace if preceded by reflexive or action verb
                has_verb = any(t.pos_ == "VERB" for t in tokens[:i])
                if has_verb:
                    replacements.append((tok.idx, tok.idx + len(tok.text), article))


def _rule_adjective_order(sent, tokens, replacements):
    """R5: Move qualifying adjective from before noun to after (English→Spanish order)."""
    for i, tok in enumerate(tokens):
        if (tok.pos_ == "ADJ"
                and tok.text.lower() in _POSTPOSITIVE_ADJS
                and i + 1 < len(tokens)
                and tokens[i + 1].pos_ == "NOUN"):
            adj = tok
            noun = tokens[i + 1]
            # Build "noun adj" to replace "adj noun"
            new_text = noun.text + ' ' + adj.text
            replacements.append((adj.idx, noun.idx + len(noun.text), new_text))


def _rule_estar_gerund(sent, tokens, replacements):
    """R6: 'Estaba + gerund' → simple imperfect (more natural in Spanish)."""
    for i, tok in enumerate(tokens):
        if (tok.lemma_ == "estar"
                and tok.text.lower() in ("estaba", "estaban")
                and i + 1 < len(tokens)):
            next_tok = tokens[i + 1]
            gerund = next_tok.text.lower()
            if gerund in _GERUND_MAP:
                imperfect = _GERUND_MAP[gerund]
                # "estaban" → need plural form
                if tok.text.lower() == "estaban":
                    # -aba → -aban, -ía → -ían
                    if imperfect.endswith("aba"):
                        imperfect = imperfect + "n"
                    elif imperfect.endswith("ía"):
                        imperfect = imperfect + "n"
                # Preserve capitalization
                if tok.text[0].isupper():
                    imperfect = imperfect[0].upper() + imperfect[1:]
                replacements.append((tok.idx, next_tok.idx + len(next_tok.text), imperfect))


def _rule_passive_to_refleja(sent, tokens, replacements):
    """R7: 'ser + participio' without 'por' agent → pasiva refleja 'se + verb'."""
    SER_FORMS = {"es", "son", "fue", "fueron", "era", "eran"}
    for i, tok in enumerate(tokens):
        if tok.text.lower() in SER_FORMS and i + 1 < len(tokens):
            part = tokens[i + 1]
            # Check it's a participle (VerbForm=Part or ends in -ado/-ido)
            is_participle = (
                "Part" in part.morph.get("VerbForm", [])
                or re.match(r'\w+[aei]d[oa]s?$', part.text.lower())
            )
            if not is_participle:
                continue
            # Skip if followed by "por" (passive with agent is OK)
            if i + 2 < len(tokens) and tokens[i + 2].text.lower() == "por":
                continue
            # Build pasiva refleja: "se + 3rd person verb"
            word = part.text.lower()
            # -ado → -a (se considera), -ados → -an
            if word.endswith("ados"):
                verb = "se " + word[:-4] + "an"
            elif word.endswith("ado"):
                verb = "se " + word[:-3] + "a"
            elif word.endswith("adas"):
                verb = "se " + word[:-4] + "an"
            elif word.endswith("ada"):
                verb = "se " + word[:-3] + "a"
            elif word.endswith("idos"):
                verb = "se " + word[:-4] + "en"
            elif word.endswith("ido"):
                verb = "se " + word[:-3] + "e"
            elif word.endswith("idas"):
                verb = "se " + word[:-4] + "en"
            elif word.endswith("ida"):
                verb = "se " + word[:-3] + "e"
            else:
                continue
            # Preserve capitalization from original
            if tok.text[0].isupper():
                verb = verb[0].upper() + verb[1:]
            replacements.append((tok.idx, part.idx + len(part.text), verb))


def _rule_que_chains(doc, replacements):
    """R3: Collapse 'que que' into single 'que' (common in nested translation)."""
    text = doc.text
    for m in re.finditer(r'\bque\s+que\b', text, re.IGNORECASE):
        replacements.append((m.start(), m.end(), 'que'))


def _rule_varied_starters(sents, text):
    """R4: When 3+ consecutive sentences start the same way, add variation."""
    ALTERNATIVES = {
        "él": ["", "Este", "Entonces"],
        "ella": ["", "Esta", "Entonces"],
        "ellos": ["", "Estos", "Entonces"],
        "ellas": ["", "Estas", "Entonces"],
    }
    sent_list = list(sents)
    changes = []  # (start, end, new_text)

    for i in range(2, len(sent_list)):
        s0 = sent_list[i - 2]
        s1 = sent_list[i - 1]
        s2 = sent_list[i]

        w0 = list(s0)[0].text.lower() if len(s0) > 0 else ""
        w1 = list(s1)[0].text.lower() if len(s1) > 0 else ""
        w2 = list(s2)[0].text.lower() if len(s2) > 0 else ""

        if w0 == w1 == w2 and w2 in ALTERNATIVES:
            alts = [a for a in ALTERNATIVES[w2] if a != w2]
            if alts:
                first = list(s2)[0]
                new_word = alts[0]  # "" means drop the pronoun (pro-drop)
                if new_word == "":
                    # Remove pronoun + trailing space
                    end = first.idx + len(first.text)
                    while end < len(text) and text[end] == ' ':
                        end += 1
                    # Capitalize the next word
                    if end < len(text):
                        changes.append((first.idx, end, text[end].upper()))
                        # Extend to consume the lowercased char
                        changes[-1] = (first.idx, end + 1, text[end].upper())
                    else:
                        changes.append((first.idx, first.idx + len(first.text), ''))
                else:
                    changes.append((first.idx, first.idx + len(first.text), new_word))

    # Apply in reverse
    for start, end, repl in sorted(changes, key=lambda x: x[0], reverse=True):
        text = text[:start] + repl + text[end:]
    return text


def _rule_dequeismo(doc, replacements):
    """R8: Fix dequeísmo — 'de que' after verbs that don't take 'de'."""
    # Verbs that should NOT have "de" before "que":
    # creer, pensar, decir, saber, opinar, considerar, etc.
    NO_DE_VERBS = {
        "creer", "pensar", "decir", "saber", "opinar", "considerar",
        "suponer", "imaginar", "parecer", "resultar", "afirmar",
        "negar", "asegurar", "esperar", "desear", "querer",
        "necesitar", "sentir", "ver", "oír",
    }
    text = doc.text
    for m in re.finditer(r'(\w+)\s+de\s+que\b', text):
        word = m.group(1).lower()
        # Check if the preceding word is a conjugation of a no-de verb
        # Simple heuristic: match verb roots
        for verb in NO_DE_VERBS:
            root = verb[:4]  # rough stem
            if word.startswith(root):
                # Remove the "de " part
                de_start = m.start() + len(m.group(1)) + 1  # start of "de "
                de_end = de_start + 3  # "de "
                replacements.append((de_start, de_end, ''))
                break


# ═════════════════════════════════════════════
# STEP 5: OPTIONAL AI REFINEMENT
# ═════════════════════════════════════════════

def step_ai_refinement(text, provider="gemini", quality_threshold=0.85):
    """
    Apply AI refinement only if text quality is below threshold.
    Quality is estimated by multiple heuristics (literal markers, English words,
    repetition, sentence structure).
    """
    score = _estimate_quality(text)
    if score >= quality_threshold:
        return text, score, False  # quality is acceptable, skip AI

    print(f"[pipeline] Quality score {score:.2f} < {quality_threshold} → invoking AI ({provider})")

    try:
        if provider == "gemini":
            from app import _gemini
            refined = _gemini(text, is_google_result=True)
        elif provider == "claude":
            from app import _claude
            refined = _claude(text, is_google_result=True)
        else:
            return text, score, False

        # Verify AI didn't make things worse
        new_score = _estimate_quality(refined)
        if new_score < score - 0.1:
            print(f"[pipeline] AI made quality worse ({score:.2f} → {new_score:.2f}), keeping original")
            return text, score, False

        return refined, new_score, True
    except Exception as e:
        print(f"[postprocess] AI refinement error: {e}")
        return text, score, False


def _estimate_quality(text):
    """
    Estimate translation quality 0.0–1.0 using multiple heuristics.
    Lower score = more problems detected = more likely needs AI help.

    Scoring weights (each contributes to penalty):
      - Remaining bad collocations / literal patterns (heavy)
      - English words left over (heavy)
      - Missing ¿ ¡ marks (light)
      - Awkward repetition of words (medium)
      - Very long sentences without punctuation (medium)
      - Unnaturally short or fragmented output (light)
    """
    if not text.strip():
        return 1.0

    words = text.split()
    total_words = max(1, len(words))
    total_sentences = max(1, text.count('.') + text.count('?') + text.count('!'))

    penalty = 0.0  # accumulates; final score = max(0, 1 - penalty)

    # ── 1. Remaining bad collocations (should have been fixed in step 4) ──
    collocation_hits = 0
    for pattern, _ in BAD_COLLOCATIONS:
        try:
            collocation_hits += len(re.findall(pattern, text, re.IGNORECASE))
        except Exception:
            continue
    penalty += collocation_hits * 0.08

    # ── 2. Remaining literal-translation patterns ──
    literal_hits = 0
    for pattern, _ in LITERAL_TRANSLATION_PATTERNS:
        try:
            literal_hits += len(re.findall(pattern, text, re.IGNORECASE))
        except Exception:
            continue
    penalty += literal_hits * 0.08

    # ── 3. English words that shouldn't be there ──
    english_markers = re.findall(
        r'\b(?:the|and|but|with|from|that|this|have|has|was|were|been|'
        r'would|could|should|their|they|them|which|where|when|while|'
        r'because|however|although|though|before|after|about|between|'
        r'into|through|during|without|against|until)\b',
        text, re.IGNORECASE
    )
    penalty += len(english_markers) * 0.10

    # ── 4. Missing opening marks (¿ ¡) ──
    missing_question = max(0, text.count('?') - text.count('¿'))
    missing_excl = max(0, text.count('!') - text.count('¡'))
    penalty += (missing_question + missing_excl) * 0.03

    # ── 5. Word repetition (same word 3+ times in close proximity → unnatural) ──
    if total_words >= 10:
        window = min(30, total_words)
        for i in range(0, total_words - window + 1, window):
            chunk_words = [w.lower().strip('.,;:¿?¡!»«"\'()') for w in words[i:i + window]]
            from collections import Counter
            freq = Counter(w for w in chunk_words if len(w) > 4)
            for w, count in freq.items():
                if count >= 4:
                    penalty += 0.05

    # ── 6. Very long sentences (>60 words without period → probably bad structure) ──
    raw_sentences = re.split(r'[.?!]', text)
    for s in raw_sentences:
        s_words = len(s.split())
        if s_words > 60:
            penalty += 0.06

    # ── 7. Fragmented output (many very short sentences → choppy translation) ──
    short_sentences = sum(1 for s in raw_sentences if 0 < len(s.split()) <= 3)
    if total_sentences >= 3 and short_sentences / total_sentences > 0.5:
        penalty += 0.10

    score = max(0.0, min(1.0, 1.0 - penalty))
    return round(score, 2)


# ═════════════════════════════════════════════
# MAIN PIPELINE
# ═════════════════════════════════════════════

def run_pipeline(text, use_ai=True, ai_provider="gemini", quality_threshold=0.85):
    """
    Run the full post-processing pipeline on a paragraph.

    AI refinement (step 5) is enabled by default but only fires when the
    quality score falls below the threshold — i.e. when there are many
    remaining errors or the text reads unnaturally.

    Args:
        text: Translated Spanish text (one paragraph)
        use_ai: Whether AI refinement is allowed (default True)
        ai_provider: "gemini" or "claude"
        quality_threshold: AI only runs if quality score < this (0.0–1.0)

    Returns:
        dict with keys: text, steps_applied, quality_score, ai_used
    """
    if not text or not text.strip():
        return {"text": text, "steps_applied": [], "quality_score": 1.0, "ai_used": False}

    steps_applied = []
    original = text

    # Step 1: Normalize
    try:
        text = step_normalize(text)
        if text != original:
            steps_applied.append("normalize")
    except Exception as e:
        print(f"[pipeline] Step 1 (normalize) failed: {e}")

    # Step 2: Hunspell spellcheck
    prev = text
    try:
        text = step_hunspell(text)
        if text != prev:
            steps_applied.append("hunspell")
    except Exception as e:
        print(f"[pipeline] Step 2 (hunspell) failed: {e}")

    # Step 3: LanguageTool grammar
    prev = text
    try:
        text = step_languagetool(text)
        if text != prev:
            steps_applied.append("languagetool")
    except Exception as e:
        print(f"[pipeline] Step 3 (languagetool) failed: {e}")

    # Step 4: Linguistic improvement (spaCy + rules)
    prev = text
    try:
        text = step_linguistic(text)
        if text != prev:
            steps_applied.append("linguistic")
    except Exception as e:
        print(f"[pipeline] Step 4 (linguistic) failed: {e}")

    # Step 5: Optional AI refinement
    ai_used = False
    quality_score = _estimate_quality(text)

    if use_ai:
        try:
            text, quality_score, ai_used = step_ai_refinement(
                text, provider=ai_provider, quality_threshold=quality_threshold
            )
            if ai_used:
                steps_applied.append("ai_refinement")
                # Re-normalize after AI (AI can introduce formatting issues)
                text = step_normalize(text)
        except Exception as e:
            print(f"[pipeline] Step 5 (AI refinement) failed: {e}")

    return {
        "text": text,
        "steps_applied": steps_applied,
        "quality_score": quality_score,
        "ai_used": ai_used,
    }


def run_pipeline_batch(texts, use_ai=True, ai_provider="gemini",
                       quality_threshold=0.85, progress_callback=None):
    """
    Process multiple paragraphs through the pipeline efficiently.

    Optimizations over calling run_pipeline() in a loop:
      - LanguageTool: batches paragraphs into fewer API calls with caching
      - spaCy: processes all texts with nlp.pipe() in one pass
      - Steps 1/2/4-regex run per-paragraph (fast, no I/O)
      - Step 5 (AI) still runs per-paragraph (rate-limited API)

    Args:
        texts: list of Spanish paragraph strings
        use_ai: whether AI step is allowed
        ai_provider: "gemini" or "claude"
        quality_threshold: AI fires below this score
        progress_callback: optional fn(done, total) called after each paragraph

    Returns:
        list of result dicts (same format as run_pipeline)
    """
    if not texts:
        return []

    total = len(texts)
    results = [None] * total

    # ── Step 1+2: Normalize + Hunspell (fast, per-paragraph) ──
    normalized = []
    steps_per = [[] for _ in range(total)]
    for i, text in enumerate(texts):
        if not text or not text.strip():
            results[i] = {"text": text, "steps_applied": [], "quality_score": 1.0, "ai_used": False}
            normalized.append(text or '')
            continue
        original = text
        try:
            text = step_normalize(text)
            if text != original:
                steps_per[i].append("normalize")
        except Exception as e:
            print(f"[pipeline-batch] Normalize failed for paragraph {i}: {e}")

        prev = text
        try:
            text = step_hunspell(text)
            if text != prev:
                steps_per[i].append("hunspell")
        except Exception as e:
            print(f"[pipeline-batch] Hunspell failed for paragraph {i}: {e}")

        normalized.append(text)

    # ── Step 3: LanguageTool (batched, fewer API calls) ──
    lt_input = []
    lt_indices = []  # indices into normalized that need LT
    for i, text in enumerate(normalized):
        if results[i] is not None:  # already done (empty text)
            continue
        lt_input.append(text)
        lt_indices.append(i)

    try:
        lt_results = step_languagetool_batch(lt_input)
        for j, idx in enumerate(lt_indices):
            if lt_results[j] != normalized[idx]:
                steps_per[idx].append("languagetool")
                normalized[idx] = lt_results[j]
    except Exception as e:
        print(f"[pipeline-batch] LanguageTool batch failed: {e}")

    # ── Step 4: Linguistic rules (regex always, spaCy batched via nlp.pipe) ──
    # Phase A+B: regex + spanish_rules (per-paragraph, fast)
    for i in lt_indices:
        prev = normalized[i]
        try:
            text = normalized[i]
            for pattern, replacement in BAD_COLLOCATIONS:
                try:
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                except Exception:
                    continue
            for pattern, replacement in LITERAL_TRANSLATION_PATTERNS:
                try:
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                except Exception:
                    continue
            try:
                try:
                    from spanish_rules import apply_spanish_rules
                except ImportError:
                    from backend.spanish_rules import apply_spanish_rules
                text = apply_spanish_rules(text)
            except Exception as e:
                print(f"[pipeline-batch] spanish_rules error: {e}")
            normalized[i] = text
            if text != prev:
                steps_per[i].append("linguistic")
        except Exception as e:
            print(f"[pipeline-batch] Linguistic regex failed for paragraph {i}: {e}")

    # Phase C: spaCy batched (one nlp.pipe call for all paragraphs)
    nlp = _get_spacy_nlp()
    if nlp is not None:
        spacy_texts = [normalized[i] for i in lt_indices]
        try:
            docs = list(nlp.pipe(spacy_texts, batch_size=50))
            for j, idx in enumerate(lt_indices):
                prev = normalized[idx]
                try:
                    improved = _spacy_improve_from_doc(docs[j])
                    if improved != prev:
                        normalized[idx] = improved
                        if "linguistic" not in steps_per[idx]:
                            steps_per[idx].append("linguistic")
                except Exception as e:
                    print(f"[pipeline-batch] spaCy improve failed for paragraph {idx}: {e}")
        except Exception as e:
            print(f"[pipeline-batch] nlp.pipe failed: {e}")

    # ── Step 5: AI refinement (per-paragraph, only if quality is low) ──
    done_count = 0
    for i in range(total):
        if results[i] is not None:
            done_count += 1
            if progress_callback:
                progress_callback(done_count, total)
            continue

        text = normalized[i]
        ai_used = False
        quality_score = _estimate_quality(text)

        if use_ai:
            try:
                text, quality_score, ai_used = step_ai_refinement(
                    text, provider=ai_provider, quality_threshold=quality_threshold
                )
                if ai_used:
                    steps_per[i].append("ai_refinement")
                    text = step_normalize(text)
            except Exception as e:
                print(f"[pipeline-batch] AI refinement failed for paragraph {i}: {e}")

        results[i] = {
            "text": text,
            "steps_applied": steps_per[i],
            "quality_score": quality_score,
            "ai_used": ai_used,
        }
        done_count += 1
        if progress_callback:
            progress_callback(done_count, total)

    return results
