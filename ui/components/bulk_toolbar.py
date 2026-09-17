"""
ui/components/bulk_toolbar.py
─────────────────────────────
Multi-select hint strip & bulk actions toolbar for DotGhostBoard Dashboard.

v2.0.0 Cerberus — Phase 6 Dashboard Decomposition.
Owns only the UI presentation and emits semantic signals when actions
are clicked. Executes zero database or storage operations.
"""

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class BulkToolbar(QObject):
    """
    Manager for the multi-select UI widgets:
      1. HintStrip: keyboard shortcut guide for multi-selection.
      2. BulkBar: action buttons appearing when 2+ cards are selected
         (Pin All, Unpin All, Add Tag, Export, Delete All, Cancel).
    """

    pin_all_requested = pyqtSignal(bool)
    delete_all_requested = pyqtSignal()
    export_requested = pyqtSignal()
    add_tag_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    hint_dismissed = pyqtSignal()

    def __init__(self, parent=None, parent_widget: QWidget | None = None):
        super().__init__(parent)
        self._parent_widget = parent_widget or (parent if isinstance(parent, QWidget) else None)
        self._build_ui()

    def _build_ui(self):
        # ── 1. Multi-select Hint Strip ──
        self.hint_strip = QFrame(self._parent_widget)
        self.hint_strip.setObjectName("HintStrip")
        self.hint_strip.setFixedHeight(32)

        hint_layout = QHBoxLayout(self.hint_strip)
        hint_layout.setContentsMargins(12, 0, 8, 0)
        hint_layout.setSpacing(16)

        hint_text = QLabel(
            "Multi-select  ·  "
            "<span style='color:#8ac99d'>Ctrl+Click</span> select  ·  "
            "<span style='color:#8ac99d'>Shift+Click</span> range  ·  "
            "<span style='color:#8ac99d'>Esc</span> clear",
            self.hint_strip,
        )
        hint_text.setObjectName("HintText")
        hint_text.setTextFormat(Qt.TextFormat.RichText)

        dismiss_btn = QPushButton("✕ got it", self.hint_strip)
        dismiss_btn.setObjectName("HintDismissBtn")
        dismiss_btn.setFixedHeight(22)
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.clicked.connect(self._on_dismiss_clicked)

        hint_layout.addWidget(hint_text)
        hint_layout.addStretch()
        hint_layout.addWidget(dismiss_btn)
        self.hint_strip.show()

        # ── 2. Bulk Actions Toolbar ──
        self.bulk_bar = QFrame(self._parent_widget)
        self.bulk_bar.setObjectName("BulkBar")
        self.bulk_bar.setFixedHeight(52)

        bulk_layout = QHBoxLayout(self.bulk_bar)
        bulk_layout.setContentsMargins(16, 0, 16, 0)
        bulk_layout.setSpacing(8)

        self.bulk_count_lbl = QLabel("0 selected", self.bulk_bar)
        self.bulk_count_lbl.setObjectName("BulkCountLabel")

        btn_pin = QPushButton("📍 Pin All", self.bulk_bar)
        btn_unpin = QPushButton("📌 Unpin All", self.bulk_bar)
        btn_delete = QPushButton("✕ Delete All", self.bulk_bar)
        btn_export = QPushButton("📤 Export", self.bulk_bar)
        btn_tag = QPushButton("🏷 Add Tag", self.bulk_bar)
        btn_cancel = QPushButton("✕ Cancel", self.bulk_bar)

        btn_pin.setObjectName("BulkBtn")
        btn_unpin.setObjectName("BulkBtn")
        btn_export.setObjectName("BulkBtn")
        btn_tag.setObjectName("BulkBtn")
        btn_delete.setObjectName("BulkBtnDanger")
        btn_cancel.setObjectName("BulkBtnCancel")

        btn_pin.clicked.connect(lambda: self.pin_all_requested.emit(True))
        btn_unpin.clicked.connect(lambda: self.pin_all_requested.emit(False))
        btn_delete.clicked.connect(self.delete_all_requested.emit)
        btn_export.clicked.connect(self.export_requested.emit)
        btn_tag.clicked.connect(self.add_tag_requested.emit)
        btn_cancel.clicked.connect(self.cancel_requested.emit)

        bulk_layout.addWidget(self.bulk_count_lbl)
        bulk_layout.addStretch()
        bulk_layout.addWidget(btn_pin)
        bulk_layout.addWidget(btn_unpin)
        bulk_layout.addWidget(btn_tag)
        bulk_layout.addWidget(btn_export)
        bulk_layout.addWidget(btn_delete)
        bulk_layout.addWidget(btn_cancel)

        self.bulk_bar.hide()

    def _on_dismiss_clicked(self):
        self.hint_strip.hide()
        self.hint_dismissed.emit()

    def update_selection_count(self, count: int):
        """Update count label and show toolbar if 2+ items selected."""
        if count >= 2:
            self.bulk_count_lbl.setText(f"{count} selected")
            self.bulk_bar.show()
        else:
            self.bulk_bar.hide()

    def show_hint(self):
        self.hint_strip.show()

    def hide_hint(self):
        self.hint_strip.hide()

    def set_hint_visible(self, visible: bool):
        self.hint_strip.setVisible(visible)
