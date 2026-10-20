"""Searchable recovery selection; bulk actions apply to the visible results."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QDialogButtonBox)


class RecoverySelectionDialog(QDialog):
    def __init__(self, summaries, selected_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Choose items for recovery')
        self.resize(460, 460)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search Vault items…')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        row = QHBoxLayout()
        self.select_all = QPushButton('Select all results')
        self.clear_all = QPushButton('Deselect all results')
        row.addWidget(self.select_all)
        row.addWidget(self.clear_all)
        layout.addLayout(row)
        self.items = QListWidget()
        chosen = set(selected_ids)
        for summary in summaries:
            item = QListWidgetItem(summary.title)
            item.setData(Qt.ItemDataRole.UserRole, summary.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if summary.id in chosen else Qt.CheckState.Unchecked)
            self.items.addItem(item)
        layout.addWidget(self.items)
        self.status = QLabel()
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.filter_items)
        self.items.itemChanged.connect(self.update_status)
        self.select_all.clicked.connect(lambda: self.check_results(True))
        self.clear_all.clicked.connect(lambda: self.check_results(False))
        self.update_status()

    def selected_ids(self):
        return [self.items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.items.count())
                if self.items.item(i).checkState() == Qt.CheckState.Checked]

    def filter_items(self, text):
        query = text.casefold().strip()
        for i in range(self.items.count()):
            item = self.items.item(i)
            item.setHidden(query not in item.text().casefold())
        self.update_status()

    def check_results(self, checked):
        self.items.blockSignals(True)
        for i in range(self.items.count()):
            item = self.items.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.items.blockSignals(False)
        self.update_status()

    def update_status(self, *args):
        visible = sum(not self.items.item(i).isHidden() for i in range(self.items.count()))
        self.status.setText(f'{len(self.selected_ids())} selected · {visible} of {self.items.count()} shown')
        self.select_all.setEnabled(bool(visible))
        self.clear_all.setEnabled(bool(visible))

    def done(self, result):
        super().done(result)
        # The caller reads the selection before deleting the parent-owned dialog.
        self.search.clear()
