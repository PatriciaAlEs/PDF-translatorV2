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

# ─────────────────────────────────────────────
# Lazy-loaded singletons (thread-safe)
# ─────────────────────────────────────────────

_hunspell_lock = threading.Lock()
_hunspell_instance = None

_spacy_lock = threading.Lock()
_spacy_nlp = None

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


def _get_hunspell():
    """Lazily load Hunspell with Spanish dictionary. Thread-safe."""
    global _hunspell_instance
    if _hunspell_instance is not None:
        return _hunspell_instance
    with _hunspell_lock:
        if _hunspell_instance is not None:
            return _hunspell_instance
        try:
            import hunspell as _hunspell_mod
            # Try common dictionary paths
            dict_paths = [
                ("/usr/share/hunspell/es_ES.dic", "/usr/share/hunspell/es_ES.aff"),
                ("/usr/share/myspell/dicts/es_ES.dic", "/usr/share/myspell/dicts/es_ES.aff"),
            ]
            # Windows: look in project dir or common paths
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            dict_paths.insert(0, (
                os.path.join(backend_dir, "dicts", "es_ES.dic"),
                os.path.join(backend_dir, "dicts", "es_ES.aff"),
            ))

            for dic_path, aff_path in dict_paths:
                if os.path.exists(dic_path) and os.path.exists(aff_path):
                    _hunspell_instance = _hunspell_mod.HunSpell(dic_path, aff_path)
                    return _hunspell_instance

            print("[postprocess] Hunspell: Spanish dictionary not found, skipping spellcheck")
            return None
        except ImportError:
            print("[postprocess] Hunspell not installed (pip install pyhunspell), skipping spellcheck")
            return None
        except Exception as e:
            print(f"[postprocess] Hunspell init error: {e}")
            return None


def _get_spacy_nlp():
    """Lazily load spaCy with Spanish model. Thread-safe."""
    global _spacy_nlp
    if _spacy_nlp is not None:
        return _spacy_nlp
    with _spacy_lock:
        if _spacy_nlp is not None:
            return _spacy_nlp
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
            return None
        except Exception as e:
            print(f"[postprocess] spaCy init error: {e}")
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

    # Process word by word, preserving structure
    def _correct_word(word):
        # Skip short words, punctuation, numbers, proper nouns at sentence start
        if len(word) < 3:
            return word
        if _SPELLCHECK_SKIP.search(word):
            return word
        # Skip words with special chars
        clean = re.sub(r'[.,;:?!¿¡»«\'"()\[\]—]', '', word)
        if not clean or len(clean) < 3:
            return word

        try:
            if hs.spell(clean):
                return word  # word is correct
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
    """Apply grammar and punctuation corrections via LanguageTool API (Spanish)."""
    import requests as _requests

    if not text.strip():
        return text

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
        try:
            r = _requests.post(
                'https://api.languagetool.org/v2/check',
                data={'text': chunk, 'language': 'es'},
                timeout=30,
            )
            if r.status_code != 200:
                corrected_chunks.append(chunk)
                continue

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
            corrected_chunks.append(result)
        except Exception as e:
            print(f"[postprocess] LanguageTool error: {e}")
            corrected_chunks.append(chunk)

    return '\n'.join(corrected_chunks)


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
    """Use spaCy to detect and fix unnatural sentence patterns."""
    try:
        # Process in smaller chunks to avoid memory issues
        MAX_CHARS = 50000
        if len(text) > MAX_CHARS:
            mid = text[:MAX_CHARS].rfind('\n')
            if mid == -1:
                mid = MAX_CHARS
            return _spacy_improve(nlp, text[:mid]) + '\n' + _spacy_improve(nlp, text[mid + 1:])

        doc = nlp(text)

        replacements = []
        for sent in doc.sents:
            sent_text = sent.text

            # Detect excessive gerunds (English-style progressive)
            gerund_count = sum(1 for token in sent if token.pos_ == "VERB" and token.text.endswith(("ando", "iendo", "endo")))
            if gerund_count >= 3 and len(sent) > 8:
                # Flag but don't auto-fix complex cases — let other steps handle
                pass

            # Detect subject pronoun overuse (Spanish is pro-drop)
            pronouns_used = [token for token in sent if token.pos_ == "PRON" and token.dep_ == "nsubj"
                             and token.text.lower() in ("él", "ella", "yo", "nosotros", "ellos", "ellas")]
            if len(pronouns_used) >= 2:
                # Remove the second and subsequent redundant subject pronouns
                for pron in pronouns_used[1:]:
                    start = pron.idx - sent.start_char
                    end = start + len(pron.text)
                    # Only remove if followed by a space
                    full_end = end
                    while full_end < len(sent_text) and sent_text[full_end] == ' ':
                        full_end += 1
                    if full_end > end:
                        replacements.append((sent.start_char + start, sent.start_char + full_end, ''))

        # Apply replacements in reverse order
        result = text
        for start, end, repl in sorted(replacements, key=lambda x: x[0], reverse=True):
            result = result[:start] + repl + result[end:]

        return result
    except Exception as e:
        print(f"[postprocess] spaCy analysis error: {e}")
        return text


# ═════════════════════════════════════════════
# STEP 5: OPTIONAL AI REFINEMENT
# ═════════════════════════════════════════════

def step_ai_refinement(text, provider="gemini", quality_threshold=0.7):
    """
    Apply AI refinement only if text quality is below threshold.
    Quality is estimated by counting remaining literal-translation markers.
    Only runs if explicitly enabled.
    """
    score = _estimate_quality(text)
    if score >= quality_threshold:
        return text, score, False  # text is good enough, skip AI

    try:
        if provider == "gemini":
            from app import _gemini
            refined = _gemini(text, is_google_result=True)
        elif provider == "claude":
            from app import _claude
            refined = _claude(text, is_google_result=True)
        else:
            return text, score, False

        return refined, score, True
    except Exception as e:
        print(f"[postprocess] AI refinement error: {e}")
        return text, score, False


def _estimate_quality(text):
    """
    Estimate translation quality 0.0–1.0 by counting markers of literal translation.
    Lower score = more problems detected = more likely needs AI help.
    """
    if not text.strip():
        return 1.0

    problems = 0
    total_sentences = max(1, text.count('.') + text.count('?') + text.count('!'))

    # Check for remaining bad collocations
    for pattern, _ in BAD_COLLOCATIONS:
        try:
            problems += len(re.findall(pattern, text, re.IGNORECASE))
        except Exception:
            continue

    # Check for remaining literal patterns
    for pattern, _ in LITERAL_TRANSLATION_PATTERNS:
        try:
            problems += len(re.findall(pattern, text, re.IGNORECASE))
        except Exception:
            continue

    # Check for English words that shouldn't be there
    english_markers = re.findall(
        r'\b(?:the|and|but|with|from|that|this|have|has|was|were|been|would|could|should)\b',
        text, re.IGNORECASE
    )
    problems += len(english_markers)

    # Check for missing opening marks
    problems += text.count('?') - text.count('¿')
    problems += text.count('!') - text.count('¡')

    # Normalize: more problems per sentence = lower score
    problem_ratio = problems / total_sentences
    score = max(0.0, min(1.0, 1.0 - (problem_ratio * 0.15)))
    return round(score, 2)


# ═════════════════════════════════════════════
# MAIN PIPELINE
# ═════════════════════════════════════════════

def run_pipeline(text, use_ai=False, ai_provider="gemini", quality_threshold=0.7):
    """
    Run the full post-processing pipeline on a paragraph.

    Args:
        text: Translated Spanish text (one paragraph)
        use_ai: Whether to enable optional AI refinement (step 5)
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
