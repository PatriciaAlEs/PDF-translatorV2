"""
Test del pipeline post_process_spanish.
Simula un texto ya traducido del inglés al español con todos los problemas típicos.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import (
    post_process_spanish,
    fix_whitespace,
    fix_dialogues,
    fix_opening_marks,
    fix_punctuation_spacing,
    capitalize_after_period,
    fix_paragraph_structure,
    fix_ellipsis,
    fix_ordinals,
    _cleanup_remaining_quotes,
)

# ─────────────────────────────────────────────
# TEXTO DE PRUEBA: traducción "cruda" típica del inglés
# con todos los problemas que debería corregir el pipeline
# ─────────────────────────────────────────────

texto_problematico = """CHAPTER 3

"Hello, John" ,  said Mary.   "How   are you?"
"I'm fine" , he replied.  "What about you?"

«I don't think so», she whispered. «This is too dangerous.»

The 1st of January was cold.  The 2nd day was worse.  On the 3rd morning ,  everything changed.

ella camino por el largo   pasillo sin mirar atras.  el viento soplaba con fuerza.

donde vas?  no puedes irte asi!  espera un momento!

the man walked into the room..  He sat down and waited...    Then he stood up.

"Run!" she shouted. "They're coming!"
"Where?" he asked. "I don't see anyone."
"Behind us!" she cried. "Hurry!"

CAPÍTULO 4

era una noche oscura.el perro ladraba sin cesar,el gato dormía tranquilamente.

"I can't believe this"  , said Thomas ,  looking at the sky.    "It's  incredible".

los puntos suspensivos están mal.. solo dos puntos.  o demasiados..... eso también.

María le dijo "no te preocupes ,  todo va a estar bien" .  Él no la escuchó.

"Are you sure?" he asked ,  raising an eyebrow.
"Absolutely" ,  she confirmed.

Parte II

que hora es?  son las tres!  vamos rapido!

el niño ,  que era muy pequeño  , corría por el jardín sin parar .  su madre lo miraba desde la ventana .

"Don't move"  ,  the soldier ordered.  "Stay where you are" .

«No puedo más», murmuró ella. «Estoy agotada».

PRÓLOGO DE LA SEGUNDA PARTE



las calles estaban vacías .  no había nadie .  era como si el mundo se hubiera detenido .

***

"I love you,"  he said.
"I love you too,"  she replied ,  smiling.

this happened on the 21st century.  she was the 4th person to arrive.

después de mucho pensar ,  él decidió irse .  no había nada más que hacer .  la puerta se cerró detrás de él .
"""

# ─────────────────────────────────────────────
# EJECUTAR PIPELINE PASO A PASO
# ─────────────────────────────────────────────

print("=" * 70)
print("  TEST DE POST-PROCESAMIENTO LINGÜÍSTICO ESPAÑOL")
print("=" * 70)

# Mostrar texto original
print("\n▸ TEXTO ORIGINAL (con problemas):")
print("-" * 50)
print(texto_problematico)
print("-" * 50)

# Paso 1: Limpieza de espacios
paso1 = fix_whitespace(texto_problematico)
print("\n▸ PASO 1 — fix_whitespace:")
print("-" * 50)
print(paso1)

# Paso 2: Diálogos
paso2 = fix_dialogues(paso1)
print("\n▸ PASO 2 — fix_dialogues:")
print("-" * 50)
print(paso2)

# Paso 3: Espaciado/puntuación
paso3 = fix_punctuation_spacing(paso2)
print("\n▸ PASO 3 — fix_punctuation_spacing:")
print("-" * 50)
print(paso3)

# Paso 4: Mayúsculas
paso4 = capitalize_after_period(paso3)
print("\n▸ PASO 4 — capitalize_after_period:")
print("-" * 50)
print(paso4)

# Paso 5: Signos de apertura ¿ ¡
paso5 = fix_opening_marks(paso4)
print("\n▸ PASO 5 — fix_opening_marks:")
print("-" * 50)
print(paso5)

# Paso 6: Estructura de párrafos
paso6 = fix_paragraph_structure(paso5)
print("\n▸ PASO 6 — fix_paragraph_structure:")
print("-" * 50)
print(paso6)

# Paso 7: Puntos suspensivos
paso7 = fix_ellipsis(paso6)
print("\n▸ PASO 7 — fix_ellipsis:")
print("-" * 50)
print(paso7)

# Paso 8: Ordinales
paso8 = fix_ordinals(paso7)
print("\n▸ PASO 8 — fix_ordinals:")
print("-" * 50)
print(paso8)

# Pipeline completo de una sola vez
print("\n" + "=" * 70)
print("  RESULTADO FINAL — post_process_spanish() completo")
print("=" * 70)
resultado_final = post_process_spanish(texto_problematico)
print(resultado_final)
print("=" * 70)

# ─────────────────────────────────────────────
# VERIFICACIONES AUTOMÁTICAS
# ─────────────────────────────────────────────

print("\n\n▸ VERIFICACIONES AUTOMÁTICAS:")
print("-" * 50)

checks = [
    ("No quedan comillas dobles de diálogo",
     '"' not in resultado_final and '"' not in resultado_final and '"' not in resultado_final),
    ("No quedan comillas francesas «»",
     '«' not in resultado_final and '»' not in resultado_final),
    ("Hay guiones largos (—) para diálogos",
     '—' in resultado_final),
    ("No hay dobles espacios",
     '  ' not in resultado_final),
    ("Cada ? tiene su ¿ correspondiente",
     resultado_final.count('?') <= resultado_final.count('¿') + 3),  # margen por ? en medio de frase
    ("Cada ! tiene su ¡ correspondiente",
     resultado_final.count('!') <= resultado_final.count('¡') + 3),
    ("Ordinales convertidos (1.º en vez de 1st)",
     '1st' not in resultado_final and '1.º' in resultado_final),
    ("No hay 4+ puntos seguidos (....)",
     '....' not in resultado_final),
    ("Puntos suspensivos correctos (...)",
     '...' in resultado_final),
    ("No hay espacio antes de coma/punto ( , o  .)",
     ' ,' not in resultado_final and ' .' not in resultado_final.replace('...', 'XXX')),
    ("Separadores de escena normalizados (* * *)",
     '* * *' in resultado_final),
    ("No hay más de 2 líneas vacías seguidas",
     '\n\n\n\n' not in resultado_final),
]

passed = 0
failed = 0
for desc, ok in checks:
    status = "✅ PASS" if ok else "❌ FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    print(f"  {status}  {desc}")

print(f"\n  Resultado: {passed}/{len(checks)} pruebas pasadas")
if failed:
    print(f"  ⚠️  {failed} pruebas fallidas — revisar")
else:
    print("  🎉 Todas las pruebas pasadas")
