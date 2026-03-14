@echo off
echo Iniciando PDF Translator...

pip install -r requirements.txt -q

cd backend
start "" python app.py

echo.
echo Servidor corriendo en http://localhost:5000
echo Abre el archivo frontend/index.html en tu navegador
echo.
pause
