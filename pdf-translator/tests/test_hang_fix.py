"""
Test: verifica que el job de traducción NO se queda colgado en "postprocessing"
cuando el post-procesamiento excede el timeout.

Simula:
  1. Un run_pipeline_batch que tarda MORE que el timeout (simula hang de LanguageTool)
  2. Verifica que el job pasa a "completed" en vez de quedarse en "postprocessing"
  3. También prueba el caso normal (sin timeout) para asegurar que no se rompió nada
"""

import sys
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TE

# ── Test 1: Simular timeout del post-procesamiento ──
print("=" * 60)
print("TEST 1: Post-procesamiento con TIMEOUT (simula hang)")
print("=" * 60)

def fake_slow_pipeline(texts, use_ai, provider):
    """Simula un run_pipeline_batch que se queda colgado (e.g. LanguageTool no responde)"""
    print("  [fake_pipeline] Iniciando... (dormirá 10s para simular hang)")
    time.sleep(10)  # Simula bloqueo
    return [{"text": t + " [procesado]", "steps_applied": ["normalize"], "quality_score": 0.9, "ai_used": False} for t in texts]

def fake_fast_pipeline(texts, use_ai, provider):
    """Simula un run_pipeline_batch que funciona correctamente"""
    print("  [fake_pipeline] Procesando rápido...")
    time.sleep(0.5)
    return [{"text": t + " [procesado]", "steps_applied": ["normalize", "linguistic"], "quality_score": 0.95, "ai_used": False} for t in texts]

# Datos de prueba
test_paragraphs = [
    "The quick brown fox jumped over the lazy dog.",
    "She said hello to everyone at the party.",
    "It was a dark and stormy night.",
    "He made his way through the crowded street.",
    "The book was very interesting and well written.",
]

def simulate_phase2(pipeline_fn, timeout_seconds, test_name):
    """Simula la Phase 2 del _translate_docx_background"""
    job = {
        "status": "postprocessing",
        "started_at": time.time(),
        "finished_at": None,
    }
    
    ordered_raw = list(test_paragraphs)
    work_items = [(i, t) for i, t in enumerate(ordered_raw)]
    
    print(f"\n  Ejecutando Phase 2 con timeout={timeout_seconds}s...")
    pp_start = time.time()
    processed = None
    
    try:
        pp_executor = ThreadPoolExecutor(max_workers=1)
        pp_future = pp_executor.submit(
            pipeline_fn, ordered_raw, False, "none"
        )
        try:
            pp_results = pp_future.result(timeout=timeout_seconds)
            processed = {work_items[j][0]: pp_results[j]["text"] for j in range(len(work_items))}
            print(f"  Phase 2 completada en {time.time() - pp_start:.1f}s")
        except _TE:
            pp_future.cancel()
            # FIX: shutdown(wait=False) para no bloquear
            pp_executor.shutdown(wait=False)
            print(f"  Phase 2 TIMEOUT ({timeout_seconds}s) — usando traducciones raw")
        else:
            pp_executor.shutdown(wait=False)
    except Exception as e:
        print(f"  Batch pipeline error: {e}")
    
    if processed is None:
        print(f"  Usando traducciones raw (sin post-procesamiento)")
        processed = {}
        for j, (idx, _) in enumerate(work_items):
            processed[idx] = ordered_raw[j]
    
    # Simula Phase 3: marcar como completado
    job["status"] = "completed"
    job["finished_at"] = time.time()
    
    elapsed = job["finished_at"] - job["started_at"]
    return job, processed, elapsed


# ── TEST 1: Timeout (pipeline lenta) ──
start = time.time()
job1, processed1, elapsed1 = simulate_phase2(fake_slow_pipeline, timeout_seconds=2, test_name="TIMEOUT")
wall_time = time.time() - start

print(f"\n  Resultado:")
print(f"    Status: {job1['status']}")
print(f"    Párrafos procesados: {len(processed1)}")
print(f"    Tiempo total: {wall_time:.1f}s")
print(f"    ¿Tiene texto?: {bool(processed1.get(0, ''))}")

assert job1["status"] == "completed", f"FAIL: status debería ser 'completed', es '{job1['status']}'"
assert wall_time < 5, f"FAIL: debió completar en <5s (timeout=2s), tardó {wall_time:.1f}s — SE QUEDÓ COLGADO"
assert len(processed1) == 5, f"FAIL: debería tener 5 párrafos, tiene {len(processed1)}"
# En caso de timeout, debe usar traducciones raw (sin "[procesado]")
assert "[procesado]" not in processed1[0], f"FAIL: en timeout debería usar texto raw, no procesado"

print(f"\n  ✅ TEST 1 PASÓ: Job completed en {wall_time:.1f}s (NO se quedó colgado)")


# ── TEST 2: Sin timeout (pipeline rápida) ── 
print("\n" + "=" * 60)
print("TEST 2: Post-procesamiento NORMAL (sin timeout)")
print("=" * 60)

start = time.time()
job2, processed2, elapsed2 = simulate_phase2(fake_fast_pipeline, timeout_seconds=10, test_name="NORMAL")
wall_time2 = time.time() - start

print(f"\n  Resultado:")
print(f"    Status: {job2['status']}")
print(f"    Párrafos procesados: {len(processed2)}")
print(f"    Tiempo total: {wall_time2:.1f}s")
print(f"    Texto[0]: {processed2.get(0, '')[:60]}...")

assert job2["status"] == "completed", f"FAIL: status debería ser 'completed', es '{job2['status']}'"
assert len(processed2) == 5, f"FAIL: debería tener 5 párrafos, tiene {len(processed2)}"
# En caso normal, DEBE tener el texto procesado
assert "[procesado]" in processed2[0], f"FAIL: debería tener texto procesado"

print(f"\n  ✅ TEST 2 PASÓ: Job completed correctamente con post-procesamiento")


# ── TEST 3: Simula el bug ORIGINAL (with context manager) ──
print("\n" + "=" * 60)
print("TEST 3: Demostración del BUG ORIGINAL (with ... as executor)")
print("=" * 60)

def simulate_phase2_BUGGY(pipeline_fn, timeout_seconds):
    """Versión ORIGINAL con el bug: usa 'with' que bloquea en __exit__"""
    job = {"status": "postprocessing", "started_at": time.time(), "finished_at": None}
    ordered_raw = list(test_paragraphs)
    work_items = [(i, t) for i, t in enumerate(ordered_raw)]
    
    processed = None
    try:
        # BUG: 'with' llama shutdown(wait=True) al salir, bloqueando indefinidamente
        with ThreadPoolExecutor(max_workers=1) as pp_executor:
            pp_future = pp_executor.submit(pipeline_fn, ordered_raw, False, "none")
            try:
                pp_results = pp_future.result(timeout=timeout_seconds)
                processed = {work_items[j][0]: pp_results[j]["text"] for j in range(len(work_items))}
            except _TE:
                pp_future.cancel()
                print(f"  [BUG] Timeout detectado, pero 'with' bloqueará en shutdown(wait=True)...")
                # Aquí el 'with' va a esperar que el thread termine → HANG
    except Exception as e:
        print(f"  Error: {e}")
    
    if processed is None:
        processed = {i: ordered_raw[i] for i in range(len(ordered_raw))}
    
    job["status"] = "completed"
    job["finished_at"] = time.time()
    return job, processed

print("\n  Ejecutando versión BUGGY con timeout=2s y pipeline lenta (10s)...")
print("  (Si tarda ~10s en vez de ~2s, confirma el bug)")

start = time.time()
job3, processed3 = simulate_phase2_BUGGY(fake_slow_pipeline, timeout_seconds=2)
wall_time3 = time.time() - start

print(f"\n  Resultado versión BUGGY:")
print(f"    Status: {job3['status']}")
print(f"    Tiempo total: {wall_time3:.1f}s")

if wall_time3 > 5:
    print(f"\n  ⚠️  CONFIRMADO: La versión original bloqueó {wall_time3:.1f}s (debían ser ~2s)")
    print(f"     Esto causaba el hang en 'finalizando...'")
else:
    print(f"\n  (Versión buggy no bloqueó esta vez — {wall_time3:.1f}s)")

# ── RESUMEN ──
print("\n" + "=" * 60)
print("RESUMEN DE TESTS")
print("=" * 60)
print(f"  TEST 1 (Fix + timeout):    ✅ {wall_time:.1f}s (esperado: ~2s)")
print(f"  TEST 2 (Fix + normal):     ✅ {wall_time2:.1f}s (esperado: ~0.5s)")  
print(f"  TEST 3 (Bug original):     {'⚠️ BLOQUEÓ' if wall_time3 > 5 else '⏱️'} {wall_time3:.1f}s (con bug: ~10s)")
print(f"\n  El fix evita que shutdown(wait=True) bloquee indefinidamente")
print(f"  cuando el post-procesamiento excede el timeout.")
