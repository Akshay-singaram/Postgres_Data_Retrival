"""
WinCC OA Historian Data Export — Tkinter GUI.

Provides date/time pickers for start and end, a sample-rate selector,
an output-directory chooser, and a progress bar that tracks the
extraction pipeline in real time.

Run:
    python gui.py
"""

import threading
from datetime import datetime, timedelta
from tkinter import (
    Tk, Button, Label, StringVar, filedialog, messagebox,
    HORIZONTAL, DISABLED, NORMAL, W, E, NSEW,
)
from tkinter import ttk

from tkcalendar import DateEntry
from tktimepicker import SpinTimePickerOld, constants

from main import run_pipeline


# ======================= defaults ========================================
DEFAULT_SAMPLE_RATE = "1s"
DEFAULT_OUTPUT_DIR = r"C:\Users\ISBL Admin\Downloads"
SAMPLE_RATE_OPTIONS = ["1s", "5s", "10s", "30s", "1min", "5min", "15min"]
# =========================================================================


class ExportApp:
    """Main application window."""

    def __init__(self, root: Tk):
        self.root = root
        self.root.title("WinCC OA — Historian Data Export")
        self.root.resizable(False, False)

        # Track whether an export is running so we don't allow double-clicks.
        self._running = False

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        root = self.root

        # ---------- row 0: Start date/time header ----------
        row = 0
        Label(root, text="Data export start:", font=("Arial", 10, "bold")
              ).grid(row=row, column=0, columnspan=5, sticky=W, **pad)

        # ---------- row 1: Start date + time ----------
        row = 1
        Label(root, text="Date:").grid(row=row, column=0, sticky=E, **pad)
        self.cal_start = DateEntry(root, date_pattern="yyyy-MM-dd", width=12)
        self.cal_start.grid(row=row, column=1, **pad)

        Label(root, text="Time:").grid(row=row, column=2, sticky=E, **pad)
        self.tm_start = SpinTimePickerOld(root)
        self.tm_start.addAll(constants.HOURS24)
        self.tm_start.grid(row=row, column=3, columnspan=2, **pad)

        # ---------- row 2: End date/time header ----------
        row = 2
        Label(root, text="Data export end:", font=("Arial", 10, "bold")
              ).grid(row=row, column=0, columnspan=5, sticky=W, **pad)

        # ---------- row 3: End date + time ----------
        row = 3
        Label(root, text="Date:").grid(row=row, column=0, sticky=E, **pad)
        self.cal_end = DateEntry(root, date_pattern="yyyy-MM-dd", width=12)
        self.cal_end.grid(row=row, column=1, **pad)

        Label(root, text="Time:").grid(row=row, column=2, sticky=E, **pad)
        self.tm_end = SpinTimePickerOld(root)
        self.tm_end.addAll(constants.HOURS24)
        self.tm_end.grid(row=row, column=3, columnspan=2, **pad)

        # ---------- row 4: Sample rate ----------
        row = 4
        Label(root, text="Sample rate:").grid(row=row, column=0, sticky=E, **pad)
        self.sample_rate_var = StringVar(value=DEFAULT_SAMPLE_RATE)
        combo = ttk.Combobox(
            root,
            textvariable=self.sample_rate_var,
            values=SAMPLE_RATE_OPTIONS,
            width=8,
            state="readonly",
        )
        combo.grid(row=row, column=1, **pad)

        # ---------- row 5: Output directory ----------
        row = 5
        Label(root, text="Output dir:").grid(row=row, column=0, sticky=E, **pad)
        self.dir_var = StringVar(value=DEFAULT_OUTPUT_DIR)
        dir_entry = ttk.Entry(root, textvariable=self.dir_var, width=35)
        dir_entry.grid(row=row, column=1, columnspan=3, sticky=NSEW, **pad)
        Button(root, text="Browse…", command=self._browse_dir
               ).grid(row=row, column=4, **pad)

        # ---------- row 6: Export button ----------
        row = 6
        self.btn_export = Button(
            root,
            text="Export data to CSV",
            font=("Arial", 10, "bold"),
            command=self._on_export,
        )
        self.btn_export.grid(
            row=row, column=0, columnspan=5, sticky=NSEW, padx=8, pady=8,
        )

        # ---------- row 7: Progress bar ----------
        row = 7
        self.progress_var = ttk.Progressbar(
            root, orient=HORIZONTAL, length=460, mode="determinate",
        )
        self.progress_var.grid(
            row=row, column=0, columnspan=5, padx=8, pady=(0, 4),
        )

        # ---------- row 8: Status label ----------
        row = 8
        self.status_var = StringVar(value="Ready")
        Label(root, textvariable=self.status_var, anchor=W,
              font=("Arial", 9)).grid(
            row=row, column=0, columnspan=5, sticky=W, padx=8, pady=(0, 8),
        )

    # --------------------------------------------------------- callbacks
    def _browse_dir(self):
        d = filedialog.askdirectory(
            parent=self.root,
            initialdir=self.dir_var.get(),
            title="Select output directory",
        )
        if d:
            self.dir_var.set(d)

    def _collect_datetimes(self):
        """Read the date/time pickers and return (start_dt, end_dt)."""
        start_date = datetime.strptime(self.cal_start.get(), "%Y-%m-%d")
        end_date = datetime.strptime(self.cal_end.get(), "%Y-%m-%d")

        start_dt = start_date + timedelta(
            hours=self.tm_start.hours24(),
            minutes=self.tm_start.minutes(),
        )
        end_dt = end_date + timedelta(
            hours=self.tm_end.hours24(),
            minutes=self.tm_end.minutes(),
        )
        return start_dt, end_dt

    # ------------------------------------------------ progress callback
    def _update_progress(self, pct: int, msg: str):
        """Thread-safe progress update — schedules on the Tk main loop."""
        self.root.after(0, self._apply_progress, pct, msg)

    def _apply_progress(self, pct: int, msg: str):
        self.progress_var["value"] = pct
        self.status_var.set(msg)

    # ----------------------------------------------- export (threaded)
    def _on_export(self):
        if self._running:
            return

        # Validate inputs
        try:
            start_dt, end_dt = self._collect_datetimes()
        except ValueError as e:
            messagebox.showerror("Invalid date/time", str(e))
            return

        if end_dt <= start_dt:
            messagebox.showerror(
                "Invalid range",
                "End time must be after start time.",
            )
            return

        output_dir = self.dir_var.get().strip()
        if not output_dir:
            messagebox.showerror("Missing output", "Please choose an output directory.")
            return

        sample_rate = self.sample_rate_var.get()

        # Disable button & reset bar
        self._running = True
        self.btn_export.config(state=DISABLED)
        self.progress_var["value"] = 0
        self.status_var.set("Starting…")

        # Run pipeline in a background thread
        thread = threading.Thread(
            target=self._run_export,
            args=(start_dt, end_dt, sample_rate, output_dir),
            daemon=True,
        )
        thread.start()

    def _run_export(self, start_dt, end_dt, sample_rate, output_dir):
        """Runs in a background thread."""
        try:
            result = run_pipeline(
                start_dt,
                end_dt,
                sample_rate,
                output_dir,
                on_progress=self._update_progress,
            )
            if result.startswith("ERROR:"):
                self.root.after(0, messagebox.showerror, "Export failed", result)
                self.root.after(0, self._apply_progress, 0, "Failed")
            else:
                self.root.after(
                    0, messagebox.showinfo,
                    "Export complete",
                    f"CSV saved to:\n{result}",
                )
        except Exception as e:
            self.root.after(
                0, messagebox.showerror,
                "Unexpected error",
                str(e),
            )
            self.root.after(0, self._apply_progress, 0, f"Error: {e}")
        finally:
            self.root.after(0, self._finish_export)

    def _finish_export(self):
        self._running = False
        self.btn_export.config(state=NORMAL)


# ----------------------------------------------------------------- main
def main():
    root = Tk()
    ExportApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
