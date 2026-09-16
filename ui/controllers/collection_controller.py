"""
ui/controllers/collection_controller.py
───────────────────────────────────────
Controller managing collection UI interactions, sidebar state,
drag-and-drop targeting, and signal emissions.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QWidget,
)
from PyQt6.QtGui import QAction

from core.services.collection_service import CollectionService

logger = logging.getLogger(__name__)


class CollectionController(QObject):
    """
    Behavioral controller for collection management.
    Operates on an injected QListWidget and communicates state via Qt signals.
    """
    collection_selected = pyqtSignal(object)  # int | None
    collection_changed = pyqtSignal()
    item_moved_to_collection = pyqtSignal(int, object)  # item_id: int, coll_id: int | None
    status_message = pyqtSignal(str)

    def __init__(
        self,
        service: CollectionService,
        list_widget: QListWidget,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._service = service
        self._list_widget = list_widget
        self._active_collection_id: Optional[int] = None

        self._setup_widget()

    @property
    def active_collection_id(self) -> Optional[int]:
        return self._active_collection_id

    @active_collection_id.setter
    def active_collection_id(self, val: Optional[int]):
        self._active_collection_id = val

    def _setup_widget(self):
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self._list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self._list_widget.setAcceptDrops(True)
        self._list_widget.setDropIndicatorShown(True)
        self._list_widget.dragEnterEvent = self._sidebar_drag_enter
        self._list_widget.dragMoveEvent = self._sidebar_drag_move
        self._list_widget.dropEvent = self._sidebar_drop_event

    def refresh(self):
        """Reload collections from service and update the sidebar list."""
        self._list_widget.blockSignals(True)
        self._list_widget.clear()

        # Default item: All Items
        all_item = QListWidgetItem("❖ All Items")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self._list_widget.addItem(all_item)

        collections = self._service.get_collections()
        target_item = None
        for c in collections:
            item = QListWidgetItem(f"📁 {c['name']} ({c['item_count']})")
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            self._list_widget.addItem(item)
            if self._active_collection_id == c["id"]:
                target_item = item

        if target_item:
            target_item.setSelected(True)
            self._list_widget.setCurrentItem(target_item)
        else:
            all_item.setSelected(True)
            self._list_widget.setCurrentItem(all_item)
            self._active_collection_id = None

        self._list_widget.blockSignals(False)

    def _on_current_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        if not current:
            return
        coll_id = current.data(Qt.ItemDataRole.UserRole)
        self._active_collection_id = coll_id
        self.collection_selected.emit(coll_id)

    def prompt_create_collection(self, parent_widget: Optional[QWidget] = None):
        """Show input dialog to create a new collection."""
        dlg_parent = parent_widget or (self._list_widget.window() if self._list_widget else None)
        name, ok = QInputDialog.getText(
            dlg_parent, "New Collection", "Collection Name:",
            QLineEdit.EchoMode.Normal, ""
        )
        if ok and name.strip():
            clean_name = name.strip()
            self._service.create_collection(clean_name)
            self.refresh()
            self.status_message.emit(f"Collection '{clean_name}' created")
            self.collection_changed.emit()

    def prompt_rename_collection(self, coll_id: int, parent_widget: Optional[QWidget] = None):
        """Show input dialog to rename an existing collection."""
        dlg_parent = parent_widget or (self._list_widget.window() if self._list_widget else None)
        coll = self._service.get_collection(coll_id)
        old_name = coll["name"] if coll else ""
        new_name, ok = QInputDialog.getText(
            dlg_parent, "Rename Collection", "New Name:",
            QLineEdit.EchoMode.Normal, old_name
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            clean_name = new_name.strip()
            self._service.rename_collection(coll_id, clean_name)
            self.refresh()
            self.status_message.emit("Collection renamed ✓")
            self.collection_changed.emit()

    def prompt_delete_collection(self, coll_id: int, parent_widget: Optional[QWidget] = None):
        """Show confirmation dialog and delete a collection."""
        dlg_parent = parent_widget or (self._list_widget.window() if self._list_widget else None)
        reply = QMessageBox.question(
            dlg_parent, "Delete Collection",
            "Delete this collection?\n(Items will NOT be deleted, just uncategorized)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.delete_collection(coll_id)
            if self._active_collection_id == coll_id:
                self._active_collection_id = None
            self.refresh()
            self.collection_selected.emit(self._active_collection_id)
            self.status_message.emit("Collection deleted ✓")
            self.collection_changed.emit()

    def _on_context_menu(self, pos):
        item = self._list_widget.itemAt(pos)
        if not item:
            return
        coll_id = item.data(Qt.ItemDataRole.UserRole)
        if coll_id is None:
            return  # "All Items" — no rename/delete

        menu = QMenu(self._list_widget)
        menu.addAction(QAction("✏️ Rename", self._list_widget,
                               triggered=lambda: self.prompt_rename_collection(coll_id)))
        menu.addAction(QAction("🗑️ Delete", self._list_widget,
                               triggered=lambda: self.prompt_delete_collection(coll_id)))
        menu.exec(self._list_widget.mapToGlobal(pos))

    def _sidebar_drag_enter(self, event):
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.acceptProposedAction()

    def _sidebar_drag_move(self, event):
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.acceptProposedAction()

    def _sidebar_drop_event(self, event):
        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            return

        try:
            dragged_id = int(
                event.mimeData().data("application/x-dotghost-card-id").data().decode()
            )
        except (ValueError, AttributeError):
            return

        item = self._list_widget.itemAt(event.position().toPoint())
        if not item:
            return

        target_coll_id = item.data(Qt.ItemDataRole.UserRole)
        self._service.move_item_to_collection(dragged_id, target_coll_id)
        self.refresh()
        self.item_moved_to_collection.emit(dragged_id, target_coll_id)
        self.collection_changed.emit()
        self.status_message.emit("Card moved to collection ✓")
        event.acceptProposedAction()
