@echo off
cd /d "%~dp0"

if not exist python\python.exe (
    echo [Setup] Downloading Python 3.12...
    curl -L https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip -o python_embed.zip
    if errorlevel 1 ( echo Download failed. & pause & exit /b )

    echo [Setup] Extracting...
    powershell -command "Expand-Archive -Path python_embed.zip -DestinationPath python -Force"
    del python_embed.zip

    echo [Setup] Setting up pip...
    echo import site >> python\python312._pth
    curl -L https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    python\python.exe get-pip.py --quiet
    del get-pip.py

    echo [Setup] Installing packages...
    python\python.exe -m pip install streamlit==1.57.0 openai==2.37.0 python-dotenv==1.2.2 pymupdf==1.27.2.3 pdfplumber==0.11.5 openpyxl==3.1.5 --quiet

    echo [Setup] Done.
)

start http://localhost:8501
python\python.exe -m streamlit run app.py --server.headless true
pause
