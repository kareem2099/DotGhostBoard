"""
ui/tag_manager.py
─────────────────
Global Tag Manager dialog — rename, delete, or merge tags across all items.

Extracted from ui/settings.py (v1.6.0 Phantom) in v2.0.0 Cerberus
as a standalone dialog. Originally tagged W009 (v1.3.0 Wraith).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSizePolicy,
    QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt

import core.storage as storage


# ══════════════════════════════════════════════════════════════
# W009 — Tag Manager Dialog  (unchanged from v1.3.0)
# ══════════════════════════════════════════════════════════════

class TagManagerDialog(QDialog):
    """
    Global tag manager — rename, delete, or merge tags across all items.
    Opens from the Settings dialog via 'Manage Tags' button.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🏷  Manage Tags")
        self.setModal(True)
        self.setMinimumSize(360, 440)
        self.setMaximumWidth(480)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        self._build_ui()
        self._refresh_list()

    # ──────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Title ──
        title = QLabel("🏷  Tag Manager")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#e2e5e6;")
        layout.addWidget(title)

        subtitle = QLabel("Rename or delete tags globally across all items.")
        subtitle.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(subtitle)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#222;")
        layout.addWidget(sep)

        # ── Tag list ──
        self._list = QListWidget()
        self._list.setObjectName("TagManagerList")
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setStyleSheet("""
            QListWidget {
                background: #111;
                border: 1px solid #2a2a2a;
                border-radius: 6px;
            }
            QListWidget::item {
                padding: 8px 12px;
                color: #ccc;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: #18251d;
                color: #77dd98;
                border: 1px solid #31513b;
            }
            QListWidget::item:hover:!selected {
                background: #1a1a1a;
            }
        """)
        layout.addWidget(self._list)

        # ── Empty state label (shown when no tags) ──
        self._empty_lbl = QLabel("No tags yet — add some from the cards!")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color:#444; font-size:12px; padding: 20px;")
        self._empty_lbl.hide()
        layout.addWidget(self._empty_lbl)

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._rename_btn = QPushButton("✏️  Rename")
        self._rename_btn.setObjectName("TagMgrBtn")
        self._rename_btn.setToolTip("Rename selected tag across all items")
        self._rename_btn.clicked.connect(self._rename_selected)

        self._delete_btn = QPushButton("🗑️  Delete")
        self._delete_btn.setObjectName("TagMgrBtnDanger")
        self._delete_btn.setToolTip("Remove selected tag from all items")
        self._delete_btn.clicked.connect(self._delete_selected)

        self._refresh_btn = QPushButton("↻  Refresh")
        self._refresh_btn.setObjectName("TagMgrBtn")
        self._refresh_btn.setToolTip("Reload tag list from database")
        self._refresh_btn.clicked.connect(self._refresh_list)

        btn_row.addWidget(self._rename_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._refresh_btn)
        layout.addLayout(btn_row)

        # ── Status label ──
        self._status = QLabel("")
        self._status.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self._status)

        # ── Close button ──
        close_btn = QPushButton("Close")
        close_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
# ── Dialog ─────────────────────────────────────────────────────────────────────

    def _refresh_list(self):
        self._list.clear()
        tags = storage.get_all_tags()

        if not tags:
            self._list.hide()
            self._empty_lbl.show()
            self._rename_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            return

        self._empty_lbl.hide()
        self._list.show()
        self._rename_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)

        for tag in tags:
            # Count how many items use this tag
            count = len(storage.get_items_by_tag(tag))
            item  = QListWidgetItem(
                f"{tag}   ({count} item{'s' if count != 1 else ''})"
            )
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self._list.addItem(item)

        self._status.setText(
            f"{len(tags)} tag{'s' if len(tags) != 1 else ''} total"
        )

    # ──────────────────────────────────────────
    def _selected_tag(self) -> str | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ──────────────────────────────────────────
    def _rename_selected(self):
        old_tag = self._selected_tag()
        if not old_tag:
            self._status.setText("⚠ Select a tag first.")
            return

        new_tag, ok = QInputDialog.getText(
            self, "Rename Tag",
            f"Rename  {old_tag}  to:",
            text=old_tag
        )
        if not ok or not new_tag.strip():
            return

        new_tag = new_tag.strip().lower()
        if not new_tag.startswith("#"):
            new_tag = f"#{new_tag}"

        if new_tag == old_tag:
            self._status.setText("No change.")
            return

        updated = storage.rename_tag(old_tag, new_tag)
        self._status.setText(
            f"✓ Renamed {old_tag} → {new_tag}  "
            f"({updated} item{'s' if updated != 1 else ''} updated)"
        )
        self._refresh_list()

    # ──────────────────────────────────────────
    def _delete_selected(self):
        old_tag = self._selected_tag()
        if not old_tag:
            self._status.setText("⚠ Select a tag first.")
            return

        count = len(storage.get_items_by_tag(old_tag))
        reply = QMessageBox.question(
            self, "Delete Tag",
            f"Remove  {old_tag}  from {count} item{'s' if count != 1 else ''}?\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        removed = storage.delete_tag(old_tag)
        self._status.setText(
            f"✓ Deleted {old_tag}  "
            f"({removed} item{'s' if removed != 1 else ''} updated)"
        )
        self._refresh_list()
