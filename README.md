# PDF Extractor by Osama

A small desktop app: open a PDF, check or edit the extracted text, and save it
as an editable Word document (.docx) or plain text (.txt).

Everything runs on your computer, so it works offline as well as online.
No file is uploaded anywhere.

## Download (Windows)

Get `PDF-Extractor-by-Osama-Setup-1.2.0.exe` from the
[latest release](https://github.com/osama-Khan099/pdf-extractor-by-osama/releases/latest) and run it. It works on Windows 10/11
(64-bit) and needs no Python or internet. If Windows says "Windows protected
your PC", click **More info > Run anyway** (the installer isn't code-signed).

## Features

- Reads normal (text-based) PDFs directly, keeping paragraphs, headings and page breaks in DOCX.
- OCR for scanned or image-only pages (built in, no separate install needed).
  - **auto**: OCR only pages with no text layer (default)
  - **always**: OCR every page
  - **off**: never OCR
- Editable preview: fix anything before saving.
- Password-protected PDFs: it asks for the password.
- Pages appear as they're read, so you can start reading a long PDF right away.
- Find box (Ctrl+F): Enter / Shift+Enter or F3 / Shift+F3 jump to next / previous; all matches are highlighted with a count.
- Pages box: extract only a range, e.g. `1-20, 35` (blank = all pages).
- Stop keeps the pages read so far, so you can still save them.
- Shortcuts: Ctrl+O open, Ctrl+S save. You can also pass a PDF path: `python app.py file.pdf`.

## Run it (Windows, macOS, Linux)

1. Install Python 3.10+ from python.org (on Windows, tick "Add Python to PATH").
2. In this folder, run:

   ```
   pip install -r requirements.txt
   python app.py
   ```

On Linux you may also need Tk: `sudo apt install python3-tk`.

## Make an installer to share (Windows)

Double-click `build_installer.bat` on a PC that has Python. It builds the app,
then packs it into one file:

    installer\PDF-Extractor-by-Osama-Setup-1.2.0.exe

Copy that file to any Windows 10/11 PC (USB, email, Google Drive...) and run it.
It installs PDF Extractor by Osama with a Start menu entry, an optional desktop icon,
"Open with > PDF Extractor by Osama" for PDFs, and an uninstaller. The other PC does
**not** need Python or internet; everything, including OCR, is inside.

The first time, the script offers to install Inno Setup (the free tool that
makes the installer) via winget. You can also get it from https://jrsoftware.org/isdl.php.

Because the installer isn't code-signed, Windows SmartScreen may say
"Windows protected your PC" on other PCs. Click **More info > Run anyway**.

To bump the version, change `AppVersion` at the top of `installer.iss`.

## Just the app, no installer

- Windows: double-click `build_exe.bat`. The app appears at `dist\PDFExtractor\PDFExtractor.exe`
  (keep the whole `dist\PDFExtractor` folder together).
- macOS / Linux: run `./build_app.sh`.

## Files

- `app.py`: the window (Tkinter)
- `installer.iss`: installer recipe (Inno Setup)
- `extractor.py`: extraction, OCR and DOCX/TXT writing, usable on its own:

  ```python
  import extractor as ex
  doc = ex.extract("input.pdf")
  ex.save_docx(doc, "output.docx")
  ex.save_txt(doc.to_text(), "output.txt")
  ```

## Notes

- OCR quality depends on scan quality; review OCR'd text in the preview before saving.
- Complex layouts (multi-column, tables) come out as plain paragraphs, not tables.
- If you edit the preview, the DOCX is written from your edited text (one paragraph per blank-line-separated block); otherwise headings are kept.
