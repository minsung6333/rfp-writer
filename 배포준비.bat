@echo off
cd /d "%~dp0"

if exist python\ (
    echo Already configured.
    pause
    exit /b
)

echo [1/4] Downloading Python 3.12...
curl -L https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip -o python_embed.zip
if errorlevel 1 ( echo Download failed. & pause & exit /b )

echo [2/4] Extracting...
powershell -command "Expand-Archive -Path python_embed.zip -DestinationPath python -Force"
del python_embed.zip

echo [3/4] Setting up pip...
echo import site >> python\python312._pth
curl -L https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python\python.exe get-pip.py --quiet
del get-pip.py

echo [4/4] Installing packages...
python\python.exe -m pip install streamlit==1.57.0 openai==2.37.0 python-dotenv==1.2.2 pymupdf==1.27.2.3 pdfplumber==0.11.5 openpyxl==3.1.5 --quiet

echo.
echo Done!
pause
