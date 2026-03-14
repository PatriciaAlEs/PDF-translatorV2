# 📄 PDF Translator

Herramienta para subir PDFs, dividirlos en partes, traducirlos al español castellano (con Google Translate y/o IA) y volver a unirlos en un único PDF.

---

## 🚀 Instalación rápida

### 1. Requisitos previos
- Python 3.9 o superior
- pip

### 2. Instalar dependencias

```bash
cd pdf-translator
pip install -r requirements.txt
```

### 3. Configurar variables de entorno (opcional para IA)

```bash
cp .env.example .env
```

Abre `.env` y rellena tu clave de Anthropic si quieres usar la traducción con IA:
```
ANTHROPIC_API_KEY=tu_clave_aqui
```

> **Nota**: La traducción con Google funciona sin ninguna clave de API. La IA (Claude) requiere una clave de Anthropic. Obtén una en https://console.anthropic.com

---

## ▶️ Ejecutar

### Opción A — Script automático

**En Mac/Linux:**
```bash
chmod +x start.sh
./start.sh
```

**En Windows:**
```
start.bat
```

### Opción B — Manual

```bash
cd backend
python app.py
```

Luego abre el archivo `frontend/index.html` en tu navegador.

---

## 📋 Flujo de uso

```
1. SUBIR PDF
   └─ Arrastra o selecciona tu PDF

2. DIVIDIR
   └─ Elige cuántas páginas por parte (ej: 10, 20...)
   └─ Selecciona el idioma original

3. TRADUCIR PARTES
   ├─ "Traducir todo con Google" → rápido y automático
   ├─ Por parte individual:
   │   ├─ ✏️ Editar → abre el editor con el texto original
   │   ├─ 🔄 Traducir con Google → traducción automática
   │   ├─ ✨ Mejorar con IA → usa Claude para una traducción más natural
   │   └─ 💾 Guardar
   └─ Puedes editar el texto manualmente en el editor

4. GENERAR PDF
   └─ Selecciona qué partes incluir
   └─ Genera y descarga el PDF final en español
```

---

## 📁 Estructura del proyecto

```
pdf-translator/
├── backend/
│   └── app.py          # Servidor Flask con toda la lógica
├── frontend/
│   └── index.html      # Interfaz de usuario (una sola página)
├── uploads/            # PDFs subidos (temporal)
├── output/             # PDFs generados
├── sessions/           # Datos de sesiones activas
├── requirements.txt    # Dependencias Python
├── .env.example        # Plantilla de configuración
├── start.sh            # Arranque rápido (Mac/Linux)
└── start.bat           # Arranque rápido (Windows)
```

---

## 🔧 Tecnologías utilizadas

| Componente | Tecnología |
|-----------|-----------|
| Backend | Flask (Python) |
| Extracción de texto PDF | pdfplumber + pypdf |
| Traducción automática | deep-translator (Google Translate) |
| Traducción con IA | Anthropic Claude API |
| Generación PDF | reportlab |
| Frontend | HTML + CSS + JS vanilla |

---

## ⚠️ Notas importantes

- Los archivos se guardan localmente en la carpeta `sessions/`
- Para PDFs escaneados (imágenes) la extracción de texto puede fallar; se necesitaría OCR adicional
- Google Translate tiene un límite de ~5000 caracteres por petición; el código lo maneja automáticamente dividiéndolo en chunks
- La IA mejora la calidad de la traducción de Google para que suene más natural

---

## 💡 Consejos

- **Páginas por parte**: Para documentos técnicos usa 5-10 páginas. Para textos simples puedes usar 20-30.
- **Flujo recomendado**: Primero traduce todo con Google, luego usa IA en las partes más importantes.
- **Edición manual**: Puedes corregir cualquier parte directamente en el editor antes de generar el PDF final.
