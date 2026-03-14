#!/bin/bash
echo "🚀 Iniciando PDF Translator..."

# Instalar dependencias si no están
pip install -r requirements.txt -q

# Arrancar backend
cd backend
python app.py &
BACKEND_PID=$!

echo ""
echo "✅ Servidor corriendo en http://localhost:5000"
echo "📂 Abre el archivo frontend/index.html en tu navegador"
echo ""
echo "Para detener el servidor: Ctrl+C"

# Abrir navegador automáticamente (Mac)
if [[ "$OSTYPE" == "darwin"* ]]; then
  sleep 1
  open ../frontend/index.html
fi

wait $BACKEND_PID
