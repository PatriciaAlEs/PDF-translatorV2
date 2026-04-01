@echo off
echo Iniciando PDF Translator...
echo.

pip install -r requirements.txt -q

cd backend
start "" python app.py

timeout /t 2 >nul
start http://localhost:5000

echo.
echo Servidor corriendo en http://localhost:5000
echo.
pause
