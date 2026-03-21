"""
Motor de reglas lingüísticas del español para corrección de traducciones literales.

Categorías de reglas:
  1. Falsos amigos (false friends) inglés→español
  2. Calcos sintácticos (word order, literal structures)
  3. Gerundio excesivo (en español se usa menos que en inglés)
  4. Voz pasiva → pasiva refleja o activa
  5. Pronombres sujeto innecesarios (español es pro-drop)
  6. Locuciones verbales y preposicionales
  7. Conectores y muletillas de traducción literal
  8. Expresiones idiomáticas
  9. Régimen preposicional
  10. Orden adjetivo-sustantivo
"""

import re


# ─────────────────────────────────────────────
# 1. FALSOS AMIGOS (false friends)
# ─────────────────────────────────────────────

FALSE_FRIENDS = [
    # (patrón regex, reemplazo, contexto/nota)
    (r'\bactualmente\b', 'en la actualidad', None),  # actually ≠ actualmente
    (r'\brealizó\b', 'se dio cuenta de', None),  # realized → se dio cuenta
    (r'\brealizaron\b', 'se dieron cuenta de', None),
    (r'\bsoportar(?:lo|la|los|las)?\b', 'aguantar', None),  # support ≠ soportar
    (r'\beventualmente\b', 'finalmente', None),  # eventually ≠ eventualmente
    (r'\basistir a\b', 'asistir a', None),  # assist ≠ asistir (this one is correct)
    (r'\bpretender\b', 'fingir', None),  # pretend ≠ pretender
    (r'\bsensible\b', 'sensato', None),  # sensible ≠ sensible (=sensitive)
    (r'\bsimpático\b', 'agradable', None),  # sympathetic ≠ simpático
    (r'\bmolesto\b(?!\s+(?:con|por))', 'incómodo', None),  # molested context
    (r'\blargas?\b(?=\s+(?:distancia|camino|viaje|tiempo))', 'largo', None),
    (r'\bintroducir\b(?=\s+(?:a\s+)?(?:alguien|una persona))', 'presentar', None),  # introduce person
    (r'\bcarpeta\b(?=\s+(?:roja|azul|verde|del|de\s+la))', 'alfombra', None),  # carpet ≠ carpeta
    (r'\bcomprometido\b(?=\s+(?:con|a))', 'comprometido', None),  # compromised
    (r'\bdespertar\b(?=\s+(?:la|el|una|un))', 'despertar', None),
    (r'\babusó\b', 'insultó', None),  # abused → insultó/maltrató
    (r'\bignor(?:ó|aba|ar)\b', lambda m: m.group().replace('ignor', 'hizo caso omiso de' if 'ó' in m.group() else 'ignor'), None),
]

# Falsos amigos contextuales con más precisión
CONTEXTUAL_FALSE_FRIENDS = [
    # (contexto_antes_regex, palabra, contexto_después_regex, reemplazo)
    (r'(?:él|ella|yo|tú)\s+', r'realiz[óa]', r'\s+que', 'se dio cuenta de que'),
    (r'', r'aplicar(?:\s+(?:para|a)\s+)', r'(?:un|una|el|la)\s+(?:trabajo|empleo|puesto|beca)', 'solicitar'),
    (r'', r'remover', r'\s+(?:la|el|las|los|su|sus)', 'quitar'),
]


# ─────────────────────────────────────────────
# 2. CALCOS SINTÁCTICOS (literal English structures)
# ─────────────────────────────────────────────

SYNTACTIC_CALQUES = [
    # "Tener sentido" mal usado → usar "tener sentido" correctamente
    (r'\bhace sentido\b', 'tiene sentido'),
    (r'\bhacía sentido\b', 'tenía sentido'),

    # "En orden de" (in order to) → "para" / "con el fin de"
    (r'\ben orden (?:de|a)\s+', 'para '),

    # "Se supone que + infinitivo" → forma correcta
    (r'\bes supuesto\s+(?:que|de)\b', 'se supone que'),

    # "Estar siendo" (is being) → gerundio o reformulación
    (r'\bestá siendo\b', 'está'),
    (r'\bestaban siendo\b', 'estaban'),

    # "El hecho de que" excesivo
    (r'\bel hecho de que\b', 'que'),

    # "Tomar lugar" (take place) → "tener lugar" / "ocurrir"
    (r'\btomó\s+lugar\b', 'tuvo lugar'),
    (r'\btomaba\s+lugar\b', 'tenía lugar'),
    (r'\btomar\s+lugar\b', 'tener lugar'),
    (r'\btomará\s+lugar\b', 'tendrá lugar'),

    # "Dar un paseo" is fine, but "tomar un paseo" is a calque
    (r'\btomar un paseo\b', 'dar un paseo'),
    (r'\btomó un paseo\b', 'dio un paseo'),

    # "Hacer una decisión" (make a decision) → "tomar una decisión"
    (r'\bhacer\s+una\s+decisión\b', 'tomar una decisión'),
    (r'\bhizo\s+una\s+decisión\b', 'tomó una decisión'),
    (r'\bhacía\s+una\s+decisión\b', 'tomaba una decisión'),

    # "Correr un baño" (run a bath) → "preparar un baño"
    (r'\bcorr(?:er|ió|ía)\s+un\s+baño\b', 'preparar un baño'),

    # "En el otro lado" (on the other hand) → "por otro lado"
    (r'\ben el otro lado\b', 'por otro lado'),

    # "Dar la espalda a" is correct but "tornar la espalda" is a calque
    (r'\btorn(?:ar|ó)\s+(?:la|su)\s+espalda\b', lambda m: 'dar la espalda' if 'ar' in m.group() else 'dio la espalda'),

    # "Pagar atención" (pay attention) → "prestar atención"
    (r'\bpag(?:ar|ó|aba|ando)\s+atención\b', lambda m: m.group().replace('pag', 'prest')),

    # "Tomar ventaja" (take advantage) → "aprovechar(se)"
    (r'\btomó\s+ventaja\b', 'se aprovechó'),
    (r'\btomaba\s+ventaja\b', 'se aprovechaba'),
    (r'\btomar\s+ventaja\b', 'aprovecharse'),

    # "En adición a" (in addition to) → "además de"
    (r'\ben adición a\b', 'además de'),
    (r'\ben adición\b', 'además'),

    # "A pesar de que" repeated badly
    (r'\ba pesar del hecho de que\b', 'a pesar de que'),

    # "Jugar un papel/rol" (play a role) → "desempeñar un papel"
    (r'\bjug(?:ar|ó|aba)\s+un\s+(?:papel|rol)\b', lambda m: 'desempeñar un papel' if 'ar' in m.group() else 'desempeñó un papel'),
]


# ─────────────────────────────────────────────
# 3. GERUNDIO EXCESIVO
# ─────────────────────────────────────────────

GERUND_FIXES = [
    # "Estaba caminando" → "caminaba" (imperfecto es más natural en español)
    (r'\bestaba\s+(\w+)ando\b', lambda m: _gerund_to_imperfect(m, 'aba')),
    (r'\bestaba\s+(\w+)iendo\b', lambda m: _gerund_to_imperfect(m, 'ía')),

    # "Estuve caminando" → "caminé" (pretérito simple)
    (r'\bestuve\s+(\w+)ando\b', lambda m: _gerund_to_preterite(m, 'é')),
    (r'\bestuve\s+(\w+)iendo\b', lambda m: _gerund_to_preterite(m, 'í')),

    # "Siendo que" (being that) → "dado que" / "puesto que"
    (r'\bsiendo que\b', 'dado que'),

    # "Habiendo dicho eso" (having said that) → "dicho esto"
    (r'\bhabiendo dicho eso\b', 'dicho esto'),
    (r'\bhabiendo dicho esto\b', 'dicho esto'),

    # Gerundio de posterioridad (incorrecto en español)
    # "Salió corriendo, llegando a casa" → "Salió corriendo y llegó a casa"
    (r',\s+llegando\s+', ', y llegó '),
    (r',\s+causando\s+', ', lo que causó '),
    (r',\s+provocando\s+', ', lo que provocó '),
    (r',\s+resultando\s+en\s+', ', lo que resultó en '),
]


def _gerund_to_imperfect(m, ending):
    """Convert 'estaba + gerund' to imperfect tense (more natural Spanish)."""
    # Only convert common verbs to avoid wrong conjugations
    root = m.group(1)
    SAFE_ROOTS = {
        'camin': 'camin', 'habl': 'habl', 'mir': 'mir', 'pens': 'pens',
        'llor': 'llor', 'grit': 'grit', 'esper': 'esper', 'busc': 'busc',
        'intent': 'intent', 'trat': 'trat', 'trabaj': 'trabaj', 'jug': 'jug',
        'escuch': 'escuch', 'observ': 'observ', 'contempl': 'contempl',
        'com': 'com', 'beb': 'beb', 'corr': 'corr', 'le': 'le',
        'escrib': 'escrib', 'dorm': 'dorm', 'sonr': 'sonre',
    }
    if root in SAFE_ROOTS:
        return SAFE_ROOTS[root] + ending
    return m.group(0)  # Keep original if not safe


def _gerund_to_preterite(m, ending):
    """Convert 'estuve + gerund' to preterite (more natural Spanish)."""
    root = m.group(1)
    SAFE_ROOTS = {
        'camin': 'camin', 'habl': 'habl', 'mir': 'mir', 'esper': 'esper',
        'busc': 'busc', 'trabaj': 'trabaj', 'llor': 'llor',
        'com': 'com', 'beb': 'beb', 'corr': 'corr', 'le': 'le',
    }
    if root in SAFE_ROOTS:
        return SAFE_ROOTS[root] + ending
    return m.group(0)


# ─────────────────────────────────────────────
# 4. VOZ PASIVA → PASIVA REFLEJA / ACTIVA
# ─────────────────────────────────────────────

PASSIVE_FIXES = [
    # "fue + participio + por" → mantener (pasiva perifrástica necesaria con agente)
    # "fue + participio" (sin agente) → pasiva refleja "se + verbo"

    # "La puerta fue abierta" → "La puerta se abrió" / "Se abrió la puerta"
    (r'\bfue\s+(\w+)ad[oa]\b(?!\s+por\b)', lambda m: f'se {_participle_to_preterite_ar(m.group(1))}'),
    (r'\bfue\s+(\w+)id[oa]\b(?!\s+por\b)', lambda m: f'se {_participle_to_preterite_ir(m.group(1))}'),

    # "fueron + participio" (sin agente) → pasiva refleja plural
    (r'\bfueron\s+(\w+)ad[oa]s\b(?!\s+por\b)', lambda m: f'se {_participle_to_preterite_ar(m.group(1))}ron'),
    (r'\bfueron\s+(\w+)id[oa]s\b(?!\s+por\b)', lambda m: f'se {_participle_to_preterite_ir(m.group(1))}ron'),

    # "estaba siendo + participio" → simplificar
    (r'\bestaba siendo\s+(\w+)ad[oa]\b', lambda m: f'se estaba {m.group(1)}ando'),
    (r'\bestaba siendo\s+(\w+)id[oa]\b', lambda m: f'se estaba {m.group(1)}iendo'),

    # "es considerado" → "se considera"
    (r'\bes\s+considerado\b', 'se considera'),
    (r'\bson\s+considerados\b', 'se consideran'),

    # "es llamado" → "se llama"
    (r'\bes\s+llamad[oa]\b', 'se llama'),
    (r'\bson\s+llamad[oa]s\b', 'se llaman'),

    # "es dicho que" → "se dice que"
    (r'\bes\s+dicho\s+que\b', 'se dice que'),

    # "es sabido que" → "se sabe que"
    (r'\bes\s+sabido\s+que\b', 'se sabe que'),

    # "es esperado que" → "se espera que"
    (r'\bes\s+esperado\s+que\b', 'se espera que'),
]


def _participle_to_preterite_ar(root):
    """Convert -ar verb root from participle context to preterite: cerr→cerró"""
    return root + 'ó'


def _participle_to_preterite_ir(root):
    """Convert -ir/-er verb root from participle context to preterite."""
    return root + 'ió'


# ─────────────────────────────────────────────
# 5. PRONOMBRES SUJETO INNECESARIOS (pro-drop)
# ─────────────────────────────────────────────

PRONOUN_DROPS = [
    # "Él dijo" → "Dijo" (cuando el sujeto ya es claro por contexto)
    # Solo aplicar en repeticiones cercanas, no eliminar todos
    # Estos patrones eliminan pronombres redundantes antes de verbos conjugados

    # "Ella se" → "Se" (cuando el pronombre es redundante)
    (r'\bÉl\s+(dijo|pensó|susurró|murmuró|gritó|exclamó|respondió|preguntó)\b',
     lambda m: m.group(1).capitalize()),
    (r'\bElla\s+(dijo|pensó|susurró|murmuró|gritó|exclamó|respondió|preguntó)\b',
     lambda m: m.group(1).capitalize()),

    # "Yo sé" → "Sé" / "Yo creo" → "Creo" (en textos narrativos)
    (r'\bYo\s+(sé|creo|pienso|quiero|necesito|debo|puedo|tengo)\b',
     lambda m: m.group(1).capitalize()),

    # "Nosotros fuimos" → "Fuimos"
    (r'\bNosotros\s+(fuimos|éramos|somos|estamos|vamos|tenemos|queremos|podemos)\b',
     lambda m: m.group(1).capitalize()),

    # "Ellos/Ellas + verb" - less aggressive, only for clearly redundant cases
    (r'\bEllos\s+(dijeron|fueron|eran|estaban|iban|tenían|querían|podían)\b',
     lambda m: m.group(1).capitalize()),
    (r'\bEllas\s+(dijeron|fueron|eran|estaban|iban|tenían|querían|podían)\b',
     lambda m: m.group(1).capitalize()),
]


# ─────────────────────────────────────────────
# 6. LOCUCIONES VERBALES Y PREPOSICIONALES
# ─────────────────────────────────────────────

LOCUTIONS = [
    # Phrasal verbs traducidos literalmente
    (r'\bdar(?:\s+(?:para)?\s*)arriba\b', 'rendirse'),  # give up
    (r'\bdio\s+(?:para\s+)?arriba\b', 'se rindió'),
    (r'\bponer\s+(?:para\s+)?arriba\s+con\b', 'aguantar'),  # put up with
    (r'\bpuso\s+(?:para\s+)?arriba\s+con\b', 'aguantó'),
    (r'\bllevar\s+a\s+cabo\b', 'llevar a cabo'),  # (correct, keep)
    (r'\bcortar\s+(?:hacia\s+)?abajo\b', 'reducir'),  # cut down
    (r'\bcortó\s+(?:hacia\s+)?abajo\b', 'redujo'),
    (r'\bcaer\s+dormido\b', 'quedarse dormido'),  # fall asleep
    (r'\bcayó\s+dormido\b', 'se quedó dormido'),
    (r'\bcayó\s+dormida\b', 'se quedó dormida'),
    (r'\bponer(?:se)?\s+de\s+pie\b', 'levantarse'),  # stand up → ponerse de pie (correct)
    (r'\bse\s+puso\s+de\s+pie\b', 'se levantó'),
    (r'\bcorrer\s+(?:fuera|afuera)\s+de\b', 'quedarse sin'),  # run out of
    (r'\bcorrió\s+(?:fuera|afuera)\s+de\b', 'se quedó sin'),

    # Preposiciones mal traducidas
    (r'\bconsistir\s+de\b', 'consistir en'),  # consist of → consistir en
    (r'\bdepende[n]?\s+sobre\b', 'depende de'),  # depend on
    (r'\bdepender\s+sobre\b', 'depender de'),
    (r'\bpensar\s+sobre\b', 'pensar en'),  # think about → pensar en
    (r'\bsoñar\s+sobre\b', 'soñar con'),  # dream about → soñar con
    (r'\bsoñó\s+sobre\b', 'soñó con'),
    (r'\breír(?:se)?\s+sobre\b', 'reírse de'),  # laugh about → reírse de
    (r'\bpreocupar(?:se)?\s+sobre\b', 'preocuparse por'),  # worry about
    (r'\bse\s+preocupó\s+sobre\b', 'se preocupó por'),
    (r'\binsistir\s+sobre\b', 'insistir en'),  # insist on
    (r'\binsistió\s+sobre\b', 'insistió en'),
    (r'\bcontar\s+sobre\b', 'contar'),  # tell about → contar
    (r'\bcontó\s+sobre\b', 'contó'),
    (r'\bentrar\s+a\b', 'entrar en'),  # enter → entrar en (not entrar a)
    (r'\bentró\s+a\b', 'entró en'),
    (r'\bdiferent[e]\s+a\b', 'diferente de'),  # different from → diferente de
    (r'\bdiferentes\s+a\b', 'diferentes de'),
]


# ─────────────────────────────────────────────
# 7. CONECTORES Y MULETILLAS
# ─────────────────────────────────────────────

CONNECTORS = [
    # "Básicamente" excesivo (often filler from "basically")
    (r'^Básicamente,?\s+', ''),  # Remove at start of sentence

    # "Literalmente" como intensificador (literally)
    (r'\bliteralmente\s+(?=(?:murió|morí|explotó|no podía))', ''),

    # "Como que" / "tipo" (like, filler)
    (r'\bcomo que\s+', ''),

    # Sin embargo / No obstante duplicados
    (r'\bsin embargo,?\s+no obstante\b', 'sin embargo'),
    (r'\bno obstante,?\s+sin embargo\b', 'no obstante'),

    # "Al final del día" (at the end of the day) → "en definitiva"
    (r'\bal final del día\b', 'en definitiva'),

    # "En este punto en el tiempo" → "en este momento" / "ahora"
    (r'\ben este punto en el tiempo\b', 'en este momento'),

    # "De vuelta en el día" (back in the day) → "en aquella época"
    (r'\bde vuelta en el día\b', 'en aquella época'),
    (r'\bde vuelta en (?:los|aquellos) días\b', 'en aquella época'),

    # "A lo largo de" excesivo → "durante"
    (r'\ba lo largo de todo\b', 'durante todo'),
]


# ─────────────────────────────────────────────
# 8. EXPRESIONES IDIOMÁTICAS
# ─────────────────────────────────────────────

IDIOMS = [
    # Traducciones literales de idioms ingleses
    (r'\bllover gatos y perros\b', 'llover a cántaros'),  # raining cats and dogs
    (r'\bllovía gatos y perros\b', 'llovía a cántaros'),
    (r'\bun pedazo de pastel\b', 'pan comido'),  # piece of cake
    (r'\bpedazo de pastel\b', 'pan comido'),
    (r'\bmatar dos pájaros de un tiro\b', 'matar dos pájaros de un tiro'),  # (correct in Spanish)
    (r'\bla gota que derramó el vaso\b', 'la gota que colmó el vaso'),
    (r'\bderramó el vaso\b', 'colmó el vaso'),
    (r'\brompió el hielo\b', 'rompió el hielo'),  # (correct)
    (r'\ben el medio de ningún lugar\b', 'en medio de la nada'),  # middle of nowhere
    (r'\ben la mitad de ningún lugar\b', 'en medio de la nada'),
    (r'\buna vez en una luna azul\b', 'de Pascuas a Ramos'),  # once in a blue moon
    (r'\bel elefante en la habitación\b', 'el problema evidente'),  # elephant in the room
    (r'\bpatear el balde\b', 'estirar la pata'),  # kick the bucket
    (r'\bpateó el balde\b', 'estiró la pata'),
    (r'\bbajo el clima\b', 'indispuesto'),  # under the weather
    (r'\bestaba bajo el clima\b', 'estaba indispuesto'),
    (r'\bno es ciencia de cohetes\b', 'no es tan difícil'),  # it's not rocket science
    (r'\bcuesta un brazo y una pierna\b', 'cuesta un ojo de la cara'),  # costs an arm and a leg
    (r'\bcostó un brazo y una pierna\b', 'costó un ojo de la cara'),
    (r'\bmordió más de lo que podía masticar\b', 'abarcó más de lo que podía'),
    (r'\bla pelota está en tu cancha\b', 'te toca a ti'),  # ball is in your court
    (r'\babrió una lata de gusanos\b', 'abrió la caja de Pandora'),  # opened a can of worms
]


# ─────────────────────────────────────────────
# 9. ORDEN ADJETIVO-SUSTANTIVO
# ─────────────────────────────────────────────

# En español, los adjetivos calificativos van después del sustantivo (generalmente)
# "La vieja casa" puede ser correcto (literario), pero "La roja casa" suena mal
# Solo corregir patrones que suenan claramente a inglés

ADJECTIVE_ORDER = [
    # Color + sustantivo → sustantivo + color
    (r'\b(roj[oa]s?|azul(?:es)?|verde[s]?|amarill[oa]s?|blanc[oa]s?|negr[oa]s?|gris(?:es)?|naranja[s]?|morad[oa]s?|rosad[oa]s?)\s+(casa[s]?|coche[s]?|puerta[s]?|pared(?:es)?|camiseta[s]?|vestido[s]?|capa[s]?|libro[s]?|caja[s]?)\b',
     r'\2 \1'),

    # Material + sustantivo → sustantivo + "de" + material
    (r'\b(?:la|una|las|unas)\s+(madera|piedra|hierro|metal|cristal|vidrio|plástico)\s+(mesa|silla|puerta|casa|torre|pared|ventana)\b',
     r'\2 de \1'),
]


# ─────────────────────────────────────────────
# 10. MEJORAS DE NATURALIDAD NARRATIVA
# ─────────────────────────────────────────────

NARRATIVE_FIXES = [
    # "Él/Ella + verbo de movimiento" → más natural con reflexivo
    (r'\bse\s+sentó\s+(?:él|ella)\s+misma?\s+abajo\b', 'se sentó'),  # sat herself down
    (r'\bsentó\s+(?:él|ella)\s+mism[oa]\b', 'se sentó'),

    # "Hizo su camino" (made his way) → "se dirigió" / "fue"
    (r'\bhizo su camino\b', 'se dirigió'),
    (r'\bhizo su camino hacia\b', 'se dirigió hacia'),
    (r'\bhicieron su camino\b', 'se dirigieron'),

    # "No podía evitar + infinitivo" (couldn't help) → correcto, mantener
    # "No podía sino + infinitivo" → "no podía evitar"
    (r'\bno podía sino\b', 'no podía evitar'),

    # "Es como" al inicio de frase (it's like) → reformular
    (r'\bEs como si\b', 'Es como si'),  # correct, keep

    # "Un poco de" excesivo
    (r'\bun poco de un\b', 'algo'),
    (r'\bun poco de una\b', 'algo de'),

    # "Todo el repentino" (all of a sudden) → "de repente"
    (r'\btodo (?:el|de)\s+repent(?:e|ino)\b', 'de repente'),
    (r'\btodo\s+de\s+un\s+repentino\b', 'de repente'),
    (r'\bde\s+un\s+repentino\b', 'de repente'),

    # "En ese/este momento" is OK but "en este punto" is a calque
    (r'\ben este punto\b(?!\s+(?:de|del))', 'en ese momento'),

    # "Sacudió su cabeza" (shook his head) → "negó con la cabeza"
    (r'\bsacudió\s+su\s+cabeza\b', 'negó con la cabeza'),
    (r'\bsacudió\s+la\s+cabeza\b', 'negó con la cabeza'),

    # "Asintió con su cabeza" → "asintió" (redundante en español)
    (r'\basintió\s+con\s+(?:su|la)\s+cabeza\b', 'asintió'),

    # "Se encogió de hombros" → correcto, mantener
    # "Encogió sus hombros" → "se encogió de hombros"
    (r'\bencogió\s+sus\s+hombros\b', 'se encogió de hombros'),

    # "Rodó sus ojos" (rolled his eyes) → "puso los ojos en blanco"
    (r'\brodó\s+(?:sus|los)\s+ojos\b', 'puso los ojos en blanco'),

    # "Levantó una ceja" → correcto, mantener
    # "Alzó sus cejas" → "enarcó las cejas"
    (r'\balzó\s+sus\s+cejas\b', 'enarcó las cejas'),

    # "Sus ojos se ensancharon" → "abrió los ojos de par en par"
    (r'\bsus\s+ojos\s+se\s+ensancharon\b', 'abrió los ojos de par en par'),

    # "Dejó ir" (let go) → "soltó"
    (r'\bdejó\s+ir\b', 'soltó'),

    # "Dejó salir" (let out) → context dependent
    (r'\bdejó\s+salir\s+un\s+suspiro\b', 'exhaló un suspiro'),
    (r'\bdejó\s+salir\s+una\s+risa\b', 'soltó una risa'),
    (r'\bdejó\s+salir\s+un\s+grito\b', 'lanzó un grito'),

    # Posesivos redundantes (his/her traducido literal)
    # "Se lavó sus manos" → "Se lavó las manos"
    (r'\bse\s+lavó\s+sus\b', 'se lavó las'),
    (r'\bse\s+tocó\s+su\b', 'se tocó la'),
    (r'\bse\s+frotó\s+sus\b', 'se frotó las'),
    (r'\bse\s+mordió\s+su\b', 'se mordió el'),
    (r'\bse\s+rascó\s+su\b', 'se rascó la'),
    (r'\bmetió\s+sus\s+manos\b', 'metió las manos'),
    (r'\bmetió\s+su\s+mano\b', 'metió la mano'),
    (r'\blevantó\s+su\s+mano\b', 'levantó la mano'),
    (r'\blevantó\s+sus\s+manos\b', 'levantó las manos'),
    (r'\babrió\s+sus\s+ojos\b', 'abrió los ojos'),
    (r'\bcerró\s+sus\s+ojos\b', 'cerró los ojos'),
    (r'\babrió\s+su\s+boca\b', 'abrió la boca'),
    (r'\bcerró\s+su\s+boca\b', 'cerró la boca'),
    (r'\bcruzó\s+sus\s+brazos\b', 'se cruzó de brazos'),
    (r'\bcruzó\s+sus\s+piernas\b', 'cruzó las piernas'),
]


# ─────────────────────────────────────────────
# MOTOR PRINCIPAL
# ─────────────────────────────────────────────

def apply_spanish_rules(text):
    """
    Apply all Spanish linguistic rules to fix literal translations.
    Called after Google Translate and basic post-processing.
    """
    if not text or not text.strip():
        return text

    # Apply rules in order of priority
    rule_sets = [
        ("falsos_amigos", FALSE_FRIENDS),
        ("calcos", SYNTACTIC_CALQUES),
        ("gerundios", GERUND_FIXES),
        ("pasiva", PASSIVE_FIXES),
        ("pronombres", PRONOUN_DROPS),
        ("locuciones", LOCUTIONS),
        ("conectores", CONNECTORS),
        ("modismos", IDIOMS),
        ("adjetivos", ADJECTIVE_ORDER),
        ("narrativa", NARRATIVE_FIXES),
    ]

    for name, rules in rule_sets:
        for rule in rules:
            pattern = rule[0]
            replacement = rule[1]
            try:
                if callable(replacement):
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                else:
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            except Exception:
                continue  # Skip broken rules silently

    return text
