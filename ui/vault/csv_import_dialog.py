"""
ui/vault/csv_import_dialog.py
──────────────────────────────
CSV Import Dialog for The Vault.

Allows the user to:
  1. Select a CSV export from Google, Edge, Firefox, Bitwarden, 1Password,
     LastPass, or any generic password CSV.
  2. Preview the parsed entries in a table with inline password-strength badges.
  3. Filter to show only weak-password entries.
  4. Confirm the import — each entry is encrypted and stored in The Vault
     under the 'password' category.

Password strength is analysed fully offline using regex heuristics.
No internet connection or external database is required.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QSizePolicy,
)

from core.security.vault.csv_importer import CsvEntry, CsvParseResult, parse_csv_export

logger = logging.getLogger(__name__)

# ── Strength colour map ───────────────────────────────────────────────────────
_STRENGTH_COLORS = {
    "Very Weak": "#e74c3c",
    "Weak":      "#e67e22",
    "Fair":      "#f1c40f",
    "Strong":    "#2ecc71",
    "Very Strong": "#1abc9c",
    "Empty":     "#95a5a6",
    "Unknown":   "#95a5a6",
}


class _ImportWorker(QThread):
    """Background thread that bulk-imports parsed entries into the Vault."""
    progress = pyqtSignal(int)
    finished = pyqtSignal(int, int)   # (imported_count, failed_count)
    error    = pyqtSignal(str)

    def __init__(self, controller, entries: list[CsvEntry], parent=None):
        super().__init__(parent)
        self._controller = controller
        self._entries = entries

    def run(self):
        imported = 0
        failed = 0
        total = len(self._entries)
        for i, entry in enumerate(self._entries):
            try:
                self._controller.add_secret(
                    title=entry.title,
                    secret_text=entry.vault_secret_text,
                    category="password",
                )
                imported += 1
            except Exception as exc:
                logger.warning("CSV import: skipped '%s': %s", entry.title, exc)
                failed += 1
            self.progress.emit(int((i + 1) / total * 100))
        self.finished.emit(imported, failed)


class CsvImportDialog(QDialog):
    """
    Full-featured CSV import dialog with source detection, preview table,
    and offline password-strength analysis.
    """

    def __init__(self, controller, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._controller = controller
        self._parse_result: Optional[CsvParseResult] = None
        self._worker: Optional[_ImportWorker] = None

        self.setWindowTitle("📋 Import Passwords from CSV")
        self.setMinimumSize(780, 560)
        self.setModal(True)
        self.setObjectName("CsvImportDialog")

        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # ── Header ──
        hdr = QLabel("📋 Import Passwords from CSV")
        hdr.setObjectName("VaultTitle")
        hdr.setStyleSheet("font-size: 16px; font-weight: 700; color: #e2e8f0;")
        root.addWidget(hdr)

        sub = QLabel(
            "Import passwords exported from Google Chrome, Microsoft Edge, Firefox, "
            "Bitwarden, 1Password, LastPass, or any generic CSV.\n"
            "Passwords are analysed <b>offline</b> for strength — no internet required."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #94a3b8; font-size: 12px;")
        root.addWidget(sub)

        # ── File picker row ──
        file_row = QHBoxLayout()
        self._file_lbl = QLabel("No file selected")
        self._file_lbl.setStyleSheet(
            "color: #64748b; font-size: 12px; padding: 6px 10px; "
            "background: #1e293b; border-radius: 6px; border: 1px solid #334155;"
        )
        self._file_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._file_lbl.setFixedHeight(34)

        self._browse_btn = QPushButton("📂  Browse…")
        self._browse_btn.setObjectName("VaultAddBtn")
        self._browse_btn.setFixedHeight(34)
        self._browse_btn.clicked.connect(self._on_browse)

        file_row.addWidget(self._file_lbl)
        file_row.addWidget(self._browse_btn)
        root.addLayout(file_row)

        # ── Source banner ──
        self._source_lbl = QLabel("")
        self._source_lbl.setStyleSheet(
            "color: #7dd3fc; font-size: 11px; font-weight: 600; "
            "background: #0c1a2e; border-radius: 5px; padding: 4px 10px;"
        )
        self._source_lbl.hide()
        root.addWidget(self._source_lbl)

        # ── Filter row ──
        filter_row = QHBoxLayout()
        self._weak_only_chk = QCheckBox("⚠ Show weak passwords only")
        self._weak_only_chk.setStyleSheet("color: #fbbf24; font-size: 12px;")
        self._weak_only_chk.stateChanged.connect(self._apply_filter)
        self._weak_only_chk.hide()

        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._stats_lbl.hide()

        filter_row.addWidget(self._weak_only_chk)
        filter_row.addStretch()
        filter_row.addWidget(self._stats_lbl)
        root.addLayout(filter_row)

        # ── Preview table ──
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Title", "Username", "URL", "Strength", "Issues"])
        self._table.setObjectName("VaultTable")
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setStyleSheet(
            "QTableWidget { background: #0f172a; color: #e2e8f0; border: 1px solid #1e293b; "
            "gridline-color: #1e293b; border-radius: 8px; }"
            "QTableWidget::item { padding: 6px 8px; }"
            "QTableWidget::item:selected { background: #1e3a5f; }"
            "QHeaderView::section { background: #1e293b; color: #7dd3fc; padding: 6px; "
            "border: none; font-weight: 600; font-size: 11px; }"
            "QTableWidget::item:alternate { background: #0d1b2a; }"
        )
        root.addWidget(self._table)

        # ── Progress bar (hidden until import starts) ──
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { background: #1e293b; border-radius: 3px; }"
            "QProgressBar::chunk { background: #3b82f6; border-radius: 3px; }"
        )
        self._progress.hide()
        root.addWidget(self._progress)

        # ── Bottom buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("VaultToolBtn")
        self._cancel_btn.setFixedHeight(34)
        self._cancel_btn.clicked.connect(self.reject)

        self._import_btn = QPushButton("📥  Import to Vault")
        self._import_btn.setObjectName("VaultAddBtn")
        self._import_btn.setFixedHeight(34)
        self._import_btn.setEnabled(False)
        self._import_btn.clicked.connect(self._on_import)

        btn_row.addStretch()
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._import_btn)
        root.addLayout(btn_row)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Password CSV Export",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                csv_text = f.read()
            result = parse_csv_export(csv_text)
        except Exception as exc:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse CSV file:\n{exc}")
            return

        self._parse_result = result
        short_name = path.split("/")[-1]
        self._file_lbl.setText(f"📄  {short_name}")

        source_labels = {
            "google":    "Google Chrome / Google Passwords Manager",
            "edge":      "Microsoft Edge",
            "firefox":   "Mozilla Firefox",
            "bitwarden": "Bitwarden",
            "1password": "1Password",
            "lastpass":  "LastPass",
            "generic":   "Generic CSV",
        }
        src = source_labels.get(result.source, result.source.capitalize())
        self._source_lbl.setText(f"🔍 Detected source: {src}")
        self._source_lbl.show()

        self._populate_table(result.entries)
        self._update_stats()
        self._weak_only_chk.show()
        self._stats_lbl.show()
        self._import_btn.setEnabled(len(result.entries) > 0)

    def _populate_table(self, entries: list[CsvEntry]) -> None:
        self._table.setRowCount(0)
        for entry in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)

            self._table.setItem(row, 0, QTableWidgetItem(entry.title))
            self._table.setItem(row, 1, QTableWidgetItem(entry.username or "—"))
            url_display = entry.url[:40] + "…" if len(entry.url) > 40 else (entry.url or "—")
            self._table.setItem(row, 2, QTableWidgetItem(url_display))

            # Strength badge cell
            strength_item = QTableWidgetItem(f"  {entry.strength_label}  ")
            color = _STRENGTH_COLORS.get(entry.strength_label, "#94a3b8")
            strength_item.setForeground(
                __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(color)
            )
            strength_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, strength_item)

            # Issues cell
            issues = entry.strength.get("issues", [])
            issues_text = "; ".join(issues) if issues else "✓ OK"
            issues_item = QTableWidgetItem(issues_text)
            if issues:
                issues_item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#fbbf24")
                )
            else:
                issues_item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#4ade80")
                )
            self._table.setItem(row, 4, issues_item)

        self._table.resizeRowsToContents()

    def _apply_filter(self) -> None:
        if not self._parse_result:
            return
        show_weak_only = self._weak_only_chk.isChecked()
        entries = (
            [e for e in self._parse_result.entries if e.is_weak]
            if show_weak_only
            else self._parse_result.entries
        )
        self._populate_table(entries)

    def _update_stats(self) -> None:
        r = self._parse_result
        if not r:
            return
        weak_pct = int(r.weak_count / r.total_count * 100) if r.total_count else 0
        self._stats_lbl.setText(
            f"Total: {r.total_count}  •  "
            f"Weak: {r.weak_count} ({weak_pct}%)  •  "
            f"Skipped rows: {r.skipped_rows}"
        )

    def _on_import(self) -> None:
        if not self._parse_result or not self._parse_result.entries:
            return

        show_weak_only = self._weak_only_chk.isChecked()
        entries = (
            [e for e in self._parse_result.entries if e.is_weak]
            if show_weak_only
            else self._parse_result.entries
        )

        if not entries:
            QMessageBox.information(self, "Nothing to Import", "No entries match the current filter.")
            return

        confirmed = QMessageBox.question(
            self,
            "Confirm Import",
            f"Import {len(entries)} password(s) into The Vault?\n\n"
            f"Each entry will be encrypted with AES-256-GCM and stored as a 'password' secret.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        # Lock controls
        self._import_btn.setEnabled(False)
        self._browse_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._progress.setValue(0)
        self._progress.show()

        self._worker = _ImportWorker(self._controller, entries, parent=self)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_import_finished)
        self._worker.error.connect(self._on_import_error)
        self._worker.start()

    def _on_import_finished(self, imported: int, failed: int) -> None:
        self._progress.setValue(100)
        msg = f"✅ Successfully imported {imported} password(s) into The Vault."
        if failed:
            msg += f"\n⚠ {failed} entry/entries could not be imported (duplicates or errors)."
        QMessageBox.information(self, "Import Complete", msg)
        self.accept()

    def _on_import_error(self, message: str) -> None:
        QMessageBox.critical(self, "Import Error", message)
        self._import_btn.setEnabled(True)
        self._browse_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._progress.hide()
