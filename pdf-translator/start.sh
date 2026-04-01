#!/bin/bash
echo "🚀 Iniciando PDF Translator..."

pip install -r requirements.txt -q

cd backend
python app.py &
BACKEND_PID=$!

sleep 2

# Open browser automatically
if [[ "$OSTYPE" == "darwin"* ]]; then
  open http://localhost:5000
elif command -v xdg-open &> /dev/null; then
  xdg-open http://localhost:5000
fi

echo ""
echo "✅ Server running at http://localhost:5000"
echo "Press Ctrl+C to stop"
echo ""

wait $BACKEND_PID
