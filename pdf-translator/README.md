# 📄 PDF Translator v3

Traduce PDFs completos al español castellano preservando el layout, fuentes, imágenes y tablas del original. Usa Google Translate + refinamiento opcional con IA (Gemini/Claude) y post-procesamiento lingüístico automático.

**Pipeline:** PDF → DOCX → Traducir párrafos → DOCX traducido → PDF final

---

## 🚀 Instalación

### 1. Requisitos previos
- **Python 3.9+** con pip
- **Microsoft Word** instalado (necesario para la conversión DOCX → PDF vía `docx2pdf`)

### 2. Instalar dependencias

```bash
cd pdf-translator
pip install -r requirements.txt
```

### 3. Configurar claves de IA (opcional)

Crea un archivo `.env` en la carpeta `backend/` (o en la raíz):

```env
# Gemini (gratis) — https://aistudio.google.com/app/apikey
GEMINI_API_KEY=tu_clave_gemini

# Claude (opcional) — https://console.anthropic.com
ANTHROPIC_API_KEY=tu_clave_anthropic
```

> **Nota:** La traducción con Google Translate funciona sin ninguna clave. Las claves de IA solo son necesarias si marcas "Refinar con IA" en la interfaz.

---

## ▶️ Ejecutar

```bash
cd backend
python app.py
```

Abre en el navegador: **http://localhost:5000**

El servidor Flask sirve tanto el backend como el frontend automáticamente. **No necesitas abrir ningún archivo HTML directamente** — todo se accede desde `localhost:5000`.

> Los archivos `index_v2_backup.html` e `index_v3.html` en `frontend/` son backups de versiones anteriores. El archivo activo es `frontend/index.html` y se sirve automáticamente desde el servidor.

---

## 📋 Flujo de uso

```
1. SUBIR PDF
   └─ Arrastra o selecciona tu PDF
   └─ Se convierte automáticamente a DOCX (preserva layout)

2. TRADUCIR
   ├─ Selecciona idioma de origen
   ├─ Opcionalmente activa "Refinar con IA" (Gemini o Claude)
   └─ Pulsa "Traducir todo el documento"
       └─ La traducción corre en segundo plano con progreso real
       └─ Puedes ver párrafo actual, porcentaje y tiempo estimado
       └─ Se puede cancelar en cualquier momento

3. GENERAR PDF
   └─ Convierte el DOCX traducido de vuelta a PDF
   └─ Descarga el resultado final
```

---

## 📁 Estructura del proyecto

```
pdf-translator/
├── backend/
│   ├── app.py                  # Servidor Flask (API + traducción async)
│   └── app_v2_backup.py        # Backup versión anterior
├── frontend/
│   ├── index.html              # ✅ Interfaz activa (servida por Flask)
│   ├── index_v2_backup.html    # Backup v2
│   └── index_v3.html           # Backup v3
├── sessions/                   # Datos de sesiones (PDFs, DOCX, traducciones)
├── requirements.txt            # Dependencias Python
├── start.sh                    # Arranque rápido (Mac/Linux)
└── start.bat                   # Arranque rápido (Windows)
```

---

## 🔧 Tecnologías

| Componente | Tecnología |
|-----------|-----------|
| Backend | Flask + threading (traducción en segundo plano) |
| PDF → DOCX | pdf2docx (preserva layout, fuentes, imágenes, tablas) |
| DOCX → PDF | docx2pdf (a través de Microsoft Word) |
| Traducción automática | deep-translator (Google Translate, chunked) |
| Refinamiento IA | Gemini 2.0 Flash / Claude (opcional) |
| Post-procesamiento | Pipeline de 8 funciones para español literario |
| Frontend | HTML + CSS + JS vanilla (SPA) |

---

## ⚠️ Notas importantes

- **Microsoft Word** debe estar instalado para que la conversión DOCX → PDF funcione (la librería `docx2pdf` lo necesita)
- La traducción se ejecuta en segundo plano con **workers paralelos** — documentos grandes (200+ páginas) funcionan sin timeout
- Para PDFs escaneados (imágenes) se necesitaría OCR adicional
- Los archivos se guardan localmente en `sessions/`
- Google Translate tiene un límite de ~5000 caracteres por petición; el código lo divide automáticamente en chunks

---

## 💡 Consejos

- **Sin IA:** La traducción con Google es rápida (~20-50 min para 200+ páginas). Ideal para una primera pasada.
- **Con IA:** Marcar "Refinar con IA" mejora mucho la calidad literaria pero es más lento (~2-4x). Usa Gemini (gratis) para documentos largos.
- **Cancelar:** Si la traducción va demasiado lenta, puedes cancelarla y reintentar sin IA.
