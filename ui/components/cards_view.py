"""
ui/components/cards_view.py
───────────────────────────
Scroll area & layout container for clipboard cards with Drag & Drop reordering.

v2.0.0 Cerberus — Phase 6 Dashboard Decomposition.
Owns only the UI placement, scrolling, and DnD visual feedback.
Does NOT execute database queries or touch storage directly;
emits semantic signals when cards are reordered.
"""

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class CardsContainer(QWidget):
    """Inner widget that accepts drop events and forwards them to CardsView."""

    def __init__(self, cards_view: "CardsView", parent=None):
        super().__init__(parent)
        self.cards_view = cards_view
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        self.cards_view.handle_drag_enter(event)

    def dragMoveEvent(self, event):
        self.cards_view.handle_drag_move(event)

    def dropEvent(self, event):
        self.cards_view.handle_drop(event)


class CardsView(QScrollArea):
    """
    Scrollable view displaying clipboard item cards.
    Handles card addition/removal, visibility filtering, and DnD reordering.
    """

    card_reordered = pyqtSignal(int, int)  # dragged_id, target_card_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CardsScrollArea")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._drop_target_card: Optional[QWidget] = None

        self.cards_container = CardsContainer(cards_view=self, parent=self)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(12, 8, 12, 8)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        self.setWidget(self.cards_container)

    # ── Widget Placement ──────────────────────────────────────────────────────

    def add_card_widget(self, card: QWidget, at_top: bool = True):
        if at_top:
            self.cards_layout.insertWidget(0, card)
        else:
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def remove_card_widget(self, card: QWidget):
        self.cards_layout.removeWidget(card)
        card.deleteLater()

    def replace_card_widget(self, old_card: QWidget, new_card: QWidget):
        """Placement-only replacement of a card widget at the same layout index."""
        idx = self.cards_layout.indexOf(old_card)
        if idx >= 0:
            self.cards_layout.removeWidget(old_card)
            old_card.deleteLater()
            self.cards_layout.insertWidget(idx, new_card)

    def all_card_widgets(self) -> list[QWidget]:
        """Return all card widgets in visual layout order (excluding stretch)."""
        widgets = []
        for i in range(self.cards_layout.count() - 1):
            item = self.cards_layout.itemAt(i)
            if item and item.widget():
                widgets.append(item.widget())
        return widgets

    def visible_cards(self) -> list[QWidget]:
        """Return list of currently visible card widgets in visual order."""
        return [w for w in self.all_card_widgets() if w.isVisible()]

    def reorder_widgets(self, cards_in_order: list[QWidget]):
        """Re-insert all card widgets into layout matching the specified order."""
        for card in cards_in_order:
            self.cards_layout.removeWidget(card)
        for order, card in enumerate(cards_in_order):
            self.cards_layout.insertWidget(order, card)

    def ensure_card_visible(self, card: QWidget):
        self.ensureWidgetVisible(card)

    # ── Drag & Drop Event Handlers ────────────────────────────────────────────

    def handle_drag_enter(self, event):
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def handle_drag_move(self, event):
        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.ignore()
            return

        drop_pos = event.position().toPoint()
        layout = self.cards_layout
        new_target = None

        for i in range(layout.count() - 1):
            w_item = layout.itemAt(i)
            if w_item and w_item.widget() and w_item.widget().geometry().contains(drop_pos):
                new_target = w_item.widget()
                break

        if self._drop_target_card and self._drop_target_card is not new_target:
            try:
                if hasattr(self._drop_target_card, "set_drop_target"):
                    self._drop_target_card.set_drop_target(False)
            except RuntimeError:
                pass
            self._drop_target_card = None

        if new_target:
            try:
                if hasattr(new_target, "set_drop_target"):
                    new_target.set_drop_target(True)
            except RuntimeError:
                new_target = None

        self._drop_target_card = new_target
        event.acceptProposedAction()

    def handle_drop(self, event):
        if self._drop_target_card:
            try:
                if hasattr(self._drop_target_card, "set_drop_target"):
                    self._drop_target_card.set_drop_target(False)
            except RuntimeError:
                pass
            self._drop_target_card = None

        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.ignore()
            return

        try:
            dragged_id = int(
                event.mimeData().data("application/x-dotghost-card-id").data().decode()
            )
        except (ValueError, AttributeError):
            event.ignore()
            return

        drop_pos = event.position().toPoint()
        target_card = None
        layout = self.cards_layout

        for i in range(layout.count() - 1):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                target_id = getattr(w, "item_id", None)
                if w.geometry().contains(drop_pos) and target_id != dragged_id:
                    target_card = w
                    break

        if target_card is None:
            event.ignore()
            return

        target_id = getattr(target_card, "item_id", None)
        if target_id is not None:
            self.card_reordered.emit(dragged_id, target_id)
            event.acceptProposedAction()
        else:
            event.ignore()
