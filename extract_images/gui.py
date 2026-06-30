"""Simple tkinter GUI for Image Harvest."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from extract_images.cli import result_to_data, run_extraction, summarize_result


class ImageHarvestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Image Harvest")
        self.geometry("760x520")
        self.minsize(640, 420)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.dpi_var = tk.IntVar(value=300)
        self.recursive_var = tk.BooleanVar(value=True)
        self.render_scanned_var = tk.BooleanVar(value=True)
        self.report_var = tk.StringVar()

        self._messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build_ui()
        self.after(100, self._drain_messages)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(7, weight=1)

        ttk.Label(root, text="Input").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(root, textvariable=self.input_var).grid(
            row=0, column=1, sticky=tk.EW, padx=8, pady=4
        )
        ttk.Button(root, text="Browse", command=self._choose_input).grid(
            row=0, column=2, sticky=tk.E, pady=4
        )

        ttk.Label(root, text="Output").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(root, textvariable=self.output_var).grid(
            row=1, column=1, sticky=tk.EW, padx=8, pady=4
        )
        ttk.Button(root, text="Browse", command=self._choose_output).grid(
            row=1, column=2, sticky=tk.E, pady=4
        )

        ttk.Label(root, text="Report").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(root, textvariable=self.report_var).grid(
            row=2, column=1, sticky=tk.EW, padx=8, pady=4
        )
        ttk.Button(root, text="Save As", command=self._choose_report).grid(
            row=2, column=2, sticky=tk.E, pady=4
        )

        settings = ttk.Frame(root)
        settings.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=(8, 4))
        settings.columnconfigure(5, weight=1)

        ttk.Label(settings, text="DPI").grid(row=0, column=0, sticky=tk.W)
        ttk.Spinbox(
            settings,
            from_=72,
            to=1200,
            increment=50,
            textvariable=self.dpi_var,
            width=8,
        ).grid(row=0, column=1, sticky=tk.W, padx=(8, 18))
        ttk.Checkbutton(
            settings,
            text="Recursive",
            variable=self.recursive_var,
        ).grid(row=0, column=2, sticky=tk.W, padx=(0, 18))
        ttk.Checkbutton(
            settings,
            text="Render scanned PDF pages",
            variable=self.render_scanned_var,
        ).grid(row=0, column=3, sticky=tk.W)

        self.start_button = ttk.Button(root, text="Start", command=self._start)
        self.start_button.grid(row=4, column=0, sticky=tk.W, pady=(12, 8))

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.grid(row=4, column=1, columnspan=2, sticky=tk.EW, padx=8, pady=(12, 8))

        ttk.Label(root, text="Log").grid(row=6, column=0, sticky=tk.W, pady=(8, 4))
        log_frame = ttk.Frame(root)
        log_frame.grid(row=7, column=0, columnspan=3, sticky=tk.NSEW)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _choose_input(self) -> None:
        path = filedialog.askdirectory(title="Choose input directory")
        if path:
            self.input_var.set(path)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(title="Choose output directory")
        if path:
            self.output_var.set(path)

    def _choose_report(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save report",
            defaultextension=".json",
            filetypes=[
                ("JSON report", "*.json"),
                ("CSV report", "*.csv"),
                ("Text report", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.report_var.set(path)

    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        input_path = self.input_var.get().strip()
        output_path = self.output_var.get().strip()
        report_path = self.report_var.get().strip() or None

        if not input_path or not output_path:
            messagebox.showerror("Missing paths", "Choose both an input and output directory.")
            return

        try:
            dpi = int(self.dpi_var.get())
        except tk.TclError:
            messagebox.showerror("Invalid DPI", "DPI must be a number.")
            return

        if dpi <= 0:
            messagebox.showerror("Invalid DPI", "DPI must be greater than 0.")
            return

        self._set_running(True)
        self._append_log("Starting extraction...")
        self._worker = threading.Thread(
            target=self._run_worker,
            args=(Path(input_path), Path(output_path), dpi, report_path),
            daemon=True,
        )
        self._worker.start()

    def _run_worker(
        self,
        input_path: Path,
        output_path: Path,
        dpi: int,
        report_path: str | None,
    ) -> None:
        try:
            result = run_extraction(
                input_path,
                output_path,
                dpi=dpi,
                render_scanned_pages=self.render_scanned_var.get(),
                recursive=self.recursive_var.get(),
                report_path=Path(report_path) if report_path else None,
            )
        except Exception as exc:  # pragma: no cover - GUI integration path.
            self._messages.put(("error", exc))
            return

        self._messages.put(("done", result))

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, payload = self._messages.get_nowait()
                if kind == "error":
                    self._set_running(False)
                    self._append_log(f"Error: {payload}")
                    messagebox.showerror("Extraction failed", str(payload))
                elif kind == "done":
                    self._set_running(False)
                    data = result_to_data(payload)
                    summary = summarize_result(data)
                    self._append_log("Extraction complete.")
                    if "file_count" in summary:
                        self._append_log(f"Files processed: {summary['file_count']}")
                    if "image_count" in summary:
                        self._append_log(f"Images extracted: {summary['image_count']}")
                    messagebox.showinfo("Image Harvest", "Extraction complete.")
        except queue.Empty:
            pass
        self.after(100, self._drain_messages)

    def _set_running(self, running: bool) -> None:
        state = tk.DISABLED if running else tk.NORMAL
        self.start_button.configure(state=state)
        if running:
            self.progress.start(10)
        else:
            self.progress.stop()

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main() -> None:
    app = ImageHarvestApp()
    app.mainloop()


if __name__ == "__main__":
    main()
