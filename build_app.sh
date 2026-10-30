#!/bin/sh
# Builds a standalone app in dist/ (macOS or Linux).
set -e
python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --noconfirm --windowed --name PDFExtractor \
  --collect-all rapidocr_onnxruntime --collect-data pymupdf app.py
echo "Done. Your app is in dist/PDFExtractor"
