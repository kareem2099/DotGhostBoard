"""
ui/widgets/tag_chip.py
──────────────────────
TagChip widget — a single removable tag pill.
"""

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal


class TagChip(QFrame):
    """Clickable colored chip that emits sig_remove when the × is pressed."""

    sig_remove = pyqtSignal(str)   # emits the tag string e.g. "#code"

    # Rotate through a small palette so different tags get different colors
    _COLORS = [
        ("#1e3a5f", "#4a9eff"),   # blue
        ("#1e3d2f", "#4adf8a"),   # green
        ("#3d1e3f", "#cc66ff"),   # purple
        ("#3d2e1e", "#ffaa44"),   # amber
        ("#3d1e1e", "#ff6666"),   # red
        ("#1e3d3d", "#44ddcc"),   # teal
    ]
    _color_map: dict[str, tuple] = {}
    _color_idx: int = 0

    @classmethod
    def _color_for(cls, tag: str) -> tuple[str, str]:
        if tag not in cls._color_map:
            palette = cls._COLORS[cls._color_idx % len(cls._COLORS)]
            cls._color_map[tag] = palette
            cls._color_idx += 1
        return cls._color_map[tag]

    def __init__(self, tag: str, parent=None):
        super().__init__(parent)
        self.tag = tag
        bg, fg = self._color_for(tag)
        self.setObjectName("TagChip")
        self.setStyleSheet(
            f"QFrame#TagChip {{ background: {bg}; border: 1px solid {fg}44; }}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(3)

        lbl = QLabel(tag)
        lbl.setObjectName("TagChipLabel")
        lbl.setStyleSheet(f"color: {fg};")

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(14, 14)
        remove_btn.setStyleSheet(f"color: {fg}99; font-size: 13px;")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.sig_remove.emit(self.tag))

        layout.addWidget(lbl)
        layout.addWidget(remove_btn)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
