"""PDF Extractor by Osama: a small desktop app that turns a PDF into editable DOCX or TXT.

Everything runs locally, so the app works with or without internet.
Run with:  python app.py
"""

from __future__ import annotations

import bisect
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import extractor as ex

APP_TITLE = "PDF Extractor by Osama"

# Highlighting every hit of a very common word in a 500-page book would make
# the text box sluggish; past this many, only the current hit is marked.
MAX_HIGHLIGHTS = 20000


class App(tk.Tk):
    def __init__(self, initial_pdf: str | None = None):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x680")
        self.minsize(700, 420)

        self.pdf_path: str | None = None
        self.doc: ex.Document | None = None
        self.original_text = ""
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_flag = threading.Event()
        self.pages_done: list[ex.Page] = []
        self.started_at = 0.0
        self.stream_has_text = False

        self.matches: list[tuple[str, str]] = []
        self.matches_query: tuple[str, bool] | None = None
        self.matches_dirty = True
        self.find_job: str | None = None

        self.format_var = tk.StringVar(value="docx")
        self.ocr_var = tk.StringVar(value=ex.OCR_AUTO)
        self.pages_var = tk.StringVar()
        self.find_var = tk.StringVar()
        self.case_var = tk.BooleanVar(value=False)
        self.find_count_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Open a PDF to get started.")

        self._build_ui()
        self.after(100, self._poll_events)
        if initial_pdf:
            self.after(200, lambda: self.load_pdf(initial_pdf))

    # UI ---------------------------------------------------------------

    def _build_ui(self):
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")

        ttk.Button(bar, text="Open PDF...", command=self.choose_pdf).pack(side="left")
        self.file_label = ttk.Label(bar, text="No file selected", foreground="gray")
        self.file_label.pack(side="left", padx=10)
        self.reextract_btn = ttk.Button(bar, text="Re-extract", command=self.start_extract,
                                        state="disabled")
        self.reextract_btn.pack(side="right")

        opts = ttk.Frame(self, padding=(8, 0))
        opts.pack(fill="x")

        ttk.Label(opts, text="Save as:").pack(side="left")
        ttk.Radiobutton(opts, text="Word (.docx)", value="docx",
                        variable=self.format_var).pack(side="left", padx=4)
        ttk.Radiobutton(opts, text="Text (.txt)", value="txt",
                        variable=self.format_var).pack(side="left", padx=4)

        ttk.Separator(opts, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(opts, text="OCR (scanned pages):").pack(side="left")
        ocr_box = ttk.Combobox(
            opts, state="readonly", width=7, textvariable=self.ocr_var,
            values=[ex.OCR_AUTO, ex.OCR_ALWAYS, ex.OCR_OFF])
        ocr_box.pack(side="left", padx=4)
        if not ex.ocr_available():
            self.ocr_var.set(ex.OCR_OFF)
            ocr_box.configure(state="disabled")
            ttk.Label(opts, text="(OCR not installed)", foreground="gray").pack(side="left")

        ttk.Separator(opts, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(opts, text="Pages:").pack(side="left")
        pages_entry = ttk.Entry(opts, width=12, textvariable=self.pages_var)
        pages_entry.pack(side="left", padx=4)
        pages_entry.bind("<Return>", lambda e: self.start_extract())
        ttk.Label(opts, text="(blank = all, or e.g. 1-20, 35)", foreground="gray").pack(side="left")

        find_row = ttk.Frame(self, padding=(8, 8, 8, 4))
        find_row.pack(fill="x")
        ttk.Label(find_row, text="Find:").pack(side="left")
        self.find_entry = ttk.Entry(find_row, width=32, textvariable=self.find_var)
        self.find_entry.pack(side="left", padx=4)
        ttk.Button(find_row, text="Prev", width=6,
                   command=lambda: self.find(forward=False)).pack(side="left")
        ttk.Button(find_row, text="Next", width=6,
                   command=lambda: self.find(forward=True)).pack(side="left", padx=(2, 6))
        ttk.Checkbutton(find_row, text="Match case", variable=self.case_var,
                        command=self._find_live).pack(side="left")
        ttk.Label(find_row, textvariable=self.find_count_var, foreground="gray").pack(
            side="left", padx=10)
        ttk.Label(find_row, text="You can edit the text before saving.",
                  foreground="gray").pack(side="right")
        self.find_var.trace_add("write", lambda *a: self._find_live())
        self.find_entry.bind("<Return>", lambda e: self.find(forward=True))
        self.find_entry.bind("<Shift-Return>", lambda e: self.find(forward=False))
        self.find_entry.bind("<Escape>", lambda e: self.find_var.set(""))

        text_frame = ttk.Frame(self, padding=(8, 0))
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, wrap="word", undo=True, font=("Segoe UI", 11)
                            if sys.platform == "win32" else ("TkDefaultFont", 11))
        scroll = ttk.Scrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.text.tag_configure("match", background="#fff176")
        self.text.tag_configure("match_current", background="#ff9800", foreground="black")
        self.text.tag_raise("match_current")
        self.text.tag_raise("sel")
        self.text.bind("<<Modified>>", self._on_text_modified)

        bottom = ttk.Frame(self, padding=8)
        bottom.pack(fill="x")
        self.progress = ttk.Progressbar(bottom, mode="determinate", length=200)
        self.progress.pack(side="left")
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left", padx=10)
        self.save_btn = ttk.Button(bottom, text="Save...", command=self.save, state="disabled")
        self.save_btn.pack(side="right")
        self.cancel_btn = ttk.Button(bottom, text="Stop", command=self.cancel_flag.set,
                                     state="disabled")
        self.cancel_btn.pack(side="right", padx=6)

        self.bind_all("<Control-o>", lambda e: self.choose_pdf())
        self.bind_all("<Control-s>", lambda e: self.save())
        for widget in (self, self.text):
            widget.bind("<Control-f>", self._focus_find)
            widget.bind("<F3>", lambda e: self.find(forward=True))
            widget.bind("<Shift-F3>", lambda e: self.find(forward=False))

    # Actions ----------------------------------------------------------

    def choose_pdf(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(
            title="Choose a PDF", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if path:
            self.load_pdf(path)

    def load_pdf(self, path: str):
        self.pdf_path = path
        self.file_label.configure(text=os.path.basename(path), foreground="")
        self.start_extract()

    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start_extract(self, password: str | None = None):
        if not self.pdf_path or self.busy:
            return
        self.cancel_flag.clear()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.doc = None
        self.pages_done = []
        self.stream_has_text = False
        self.started_at = time.monotonic()
        self._set_busy(True)
        self.status_var.set("Opening...")
        self.progress.configure(value=0, maximum=1)
        path, mode, pages = self.pdf_path, self.ocr_var.get(), self.pages_var.get()

        def run():
            try:
                doc = ex.extract(
                    path, ocr_mode=mode, password=password, pages=pages,
                    progress=lambda d, t, m: self.events.put(("progress", d, t, m)),
                    on_page=lambda pg: self.events.put(("page", pg)),
                    cancelled=self.cancel_flag.is_set)
                self.events.put(("done", doc))
            except ex.ExtractionError as e:
                self.events.put(("error", str(e), password))
            except Exception as e:  # keep the UI alive on unexpected failures
                self.events.put(("error", f"Unexpected error: {e}", password))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def _poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "progress":
                    self._on_progress(*ev[1:])
                elif ev[0] == "page":
                    self._on_page(ev[1])
                elif ev[0] == "done":
                    self._on_done(ev[1])
                elif ev[0] == "error":
                    self._on_error(ev[1], ev[2])
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _on_progress(self, done: int, total: int, msg: str):
        self.progress.configure(maximum=max(total, 1), value=done)
        text = f"{msg}  ({done} of {total} done"
        if done:
            left = (time.monotonic() - self.started_at) / done * (total - done)
            if left >= 5:
                text += f", about {_fmt_duration(left)} left"
        self.status_var.set(text + ")")

    def _on_page(self, page: ex.Page):
        # Pages appear as they finish, so long PDFs can be read and searched
        # while the rest is still being processed.
        self.pages_done.append(page)
        chunk = "\n\n".join(p.text for p in page.paragraphs)
        if not chunk:
            return
        self.text.configure(state="normal")
        self.text.insert("end-1c", ("\n\n" if self.stream_has_text else "") + chunk)
        self.text.configure(state="disabled")
        self.stream_has_text = True

    def _on_done(self, doc: ex.Document, stopped: bool = False):
        self._set_busy(False)
        self.doc = doc
        self.original_text = doc.to_text()
        if self.text.get("1.0", "end-1c") != self.original_text:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self.original_text)
        self.text.edit_reset()
        self.matches_dirty = True
        n = len(doc.pages)
        took = _fmt_duration(time.monotonic() - self.started_at)
        msg = f"{'Stopped after' if stopped else 'Done:'} {n} page{'s' if n != 1 else ''} in {took}"
        if doc.ocr_pages:
            msg += f", OCR used on {len(doc.ocr_pages)}"
        if not self.original_text.strip():
            msg = "No text found."
            if not ex.ocr_available() or self.ocr_var.get() == ex.OCR_OFF:
                msg += " This looks like a scanned PDF; turn on OCR to read it."
        self.status_var.set(msg)
        self.save_btn.configure(state="normal" if self.original_text.strip() else "disabled")
        if self.find_var.get().strip():
            self._run_find(forward=True, include_current=True)

    def _on_error(self, message: str, tried_password: str | None):
        if message == "Cancelled." and self.pages_done:
            # Keep what was already read so it can still be saved.
            self._on_done(ex.build_document(self.pages_done), stopped=True)
            return
        self._set_busy(False)
        self.text.configure(state="normal")
        if "password" in message.lower():
            prompt = "Wrong password, try again:" if tried_password else "This PDF needs a password:"
            pw = simpledialog.askstring(APP_TITLE, prompt, show="*", parent=self)
            if pw:
                self.start_extract(password=pw)
                return
        self.status_var.set(message)
        if message != "Cancelled.":
            messagebox.showerror(APP_TITLE, message)

    def _set_busy(self, busy: bool):
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.reextract_btn.configure(state="disabled" if busy or not self.pdf_path else "normal")
        self.save_btn.configure(state="disabled")
        self.text.configure(state="disabled" if busy else "normal")
        self.configure(cursor="watch" if busy else "")

    def save(self):
        if self.busy or self.doc is None:
            return
        fmt = self.format_var.get()
        base = os.path.splitext(os.path.basename(self.pdf_path or "output"))[0]
        path = filedialog.asksaveasfilename(
            title="Save extracted text",
            initialdir=os.path.dirname(self.pdf_path or ""),
            initialfile=f"{base}.{fmt}",
            defaultextension=f".{fmt}",
            filetypes=[("Word document", "*.docx")] if fmt == "docx" else [("Text file", "*.txt")])
        if not path:
            return
        current = self.text.get("1.0", "end-1c")
        try:
            if fmt == "docx":
                edited = current.strip() != self.original_text.strip()
                ex.save_docx(self.doc, path, text=current if edited else None)
            else:
                ex.save_txt(current, path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not save file:\n{e}")
            return
        self.status_var.set(f"Saved {os.path.basename(path)}")
        if messagebox.askyesno(APP_TITLE, "Saved. Open the file now?"):
            _open_file(path)

    # Find -------------------------------------------------------------

    def _focus_find(self, _event=None):
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")
        return "break"

    def _on_text_modified(self, _event=None):
        if self.text.edit_modified():
            self.matches_dirty = True
            self.text.edit_modified(False)

    def _find_live(self):
        # Search as the user types, but wait for a short pause first.
        if self.find_job:
            self.after_cancel(self.find_job)
        self.find_job = self.after(250, lambda: self._run_find(forward=True, include_current=True))

    def find(self, forward: bool = True):
        self._run_find(forward=forward, include_current=False)
        return "break"

    def _collect_matches(self, query: str, match_case: bool):
        self.text.tag_remove("match", "1.0", "end")
        self.text.tag_remove("match_current", "1.0", "end")
        self.matches = []
        self.matches_query = (query, match_case)
        self.matches_dirty = False
        words = query.split()
        if not words:
            return
        # Any run of spaces or line breaks in the text matches a space in the query.
        pattern = re.compile(r"\s+".join(re.escape(w) for w in words),
                             0 if match_case else re.IGNORECASE)
        content = self.text.get("1.0", "end-1c")
        line_starts = [0] + [m.end() for m in re.finditer("\n", content)]

        def index(offset: int) -> str:
            line = bisect.bisect_right(line_starts, offset) - 1
            return f"{line + 1}.{offset - line_starts[line]}"

        self.matches = [(index(m.start()), index(m.end())) for m in pattern.finditer(content)]
        if len(self.matches) <= MAX_HIGHLIGHTS:
            flat = [i for pair in self.matches for i in pair]
            for k in range(0, len(flat), 2000):
                self.text.tag_add("match", *flat[k:k + 2000])

    def _first_match(self, op: str) -> int:
        """Index of the first match whose start compares `op` to the cursor."""
        lo, hi = 0, len(self.matches)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.text.compare(self.matches[mid][0], op, "insert"):
                hi = mid
            else:
                lo = mid + 1
        return lo

    def _run_find(self, forward: bool, include_current: bool):
        self.find_job = None
        query = self.find_var.get()
        key = (query, self.case_var.get())
        if self.matches_dirty or key != self.matches_query:
            self._collect_matches(*key)
        if not query.strip():
            self.find_count_var.set("")
            return
        if not self.matches:
            self.find_count_var.set("No matches")
            return
        n = len(self.matches)
        if forward:
            i = self._first_match(">=" if include_current else ">") % n
        else:
            i = (self._first_match(">=") - 1) % n
        start, end = self.matches[i]
        self.text.tag_remove("match_current", "1.0", "end")
        self.text.tag_add("match_current", start, end)
        self.text.mark_set("insert", start)
        self.text.see(start)
        self.find_count_var.set(f"{i + 1} of {n}")


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {seconds:02d} s" if minutes < 10 else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def _open_file(path: str):
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except Exception:
        pass


if __name__ == "__main__":
    App(sys.argv[1] if len(sys.argv) > 1 else None).mainloop()
