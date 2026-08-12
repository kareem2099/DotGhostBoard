"""
ui/widgets/tag_input.py
───────────────────────
TagInputRow widget — wrapping chip area + inline text input.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QCompleter
)
from PyQt6.QtCore import Qt, pyqtSignal, QStringListModel
import core.storage as storage
from .tag_chip import TagChip


class TagInputRow(QWidget):
    """
    Shows existing tags as chips and provides an inline QLineEdit
    for adding new ones.  Autocompletes from existing DB tags.
    """

    sig_tag_added   = pyqtSignal(str)   # new tag confirmed by user
    sig_tag_removed = pyqtSignal(str)   # chip × clicked

    def __init__(self, item_id: int, tags: list[str], parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.setObjectName("TagInputRow")

        # Outer wrap uses a simple VBox; chips flow in their own HBox row
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 0)
        outer.setSpacing(4)

        # ── chip row ──────────────────────────────
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(4)
        self._chip_row.addStretch()

        chip_wrap = QWidget()
        chip_wrap.setLayout(self._chip_row)
        chip_wrap.setObjectName("ChipWrap")
        outer.addWidget(chip_wrap)

        # ── tag input ─────────────────────────────
        self._input = QLineEdit()
        self._input.setObjectName("TagInput")
        self._input.setPlaceholderText("+ add tag  (#code, #python…)")
        self._input.setFixedHeight(24)
        self._input.returnPressed.connect(self._on_return)
        outer.addWidget(self._input)

        # Autocomplete from DB tags
        self._refresh_completer()

        # Render initial chips
        for tag in tags:
            self._add_chip(tag)

    # ── public ────────────────────────────────────
    def add_tag_chip(self, tag: str):
        """Called externally when a tag was successfully saved to DB."""
        self._add_chip(tag)
        self._refresh_completer()

    def remove_tag_chip(self, tag: str):
        """Remove chip visually (DB update handled by Dashboard)."""
        for i in range(self._chip_row.count()):
            item = self._chip_row.itemAt(i)
            if item and isinstance(item.widget(), TagChip):
                chip: TagChip = item.widget()
                if chip.tag == tag:
                    chip.deleteLater()
                    self._chip_row.removeItem(item)
                    break

    # ── private ───────────────────────────────────
    def _add_chip(self, tag: str):
        chip = TagChip(tag)
        chip.sig_remove.connect(self._on_chip_remove)
        # Insert before stretch (last item)
        count = self._chip_row.count()
        idx = max(0, count - 1)
        self._chip_row.insertWidget(idx, chip)

    def _on_chip_remove(self, tag: str):
        self.sig_tag_removed.emit(tag)

    def _on_return(self):
        raw = self._input.text().strip()
        if not raw:
            return
        tag = raw.lower() if raw.startswith("#") else f"#{raw.lower()}"
        self._input.clear()
        self.sig_tag_added.emit(tag)

    def _refresh_completer(self):
        all_tags = storage.get_all_tags()
        model    = QStringListModel(all_tags)
        completer = QCompleter(model, self._input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._input.setCompleter(completer)
