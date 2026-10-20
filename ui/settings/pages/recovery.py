"""Recovery settings: explicit item selection, live copies, and calendar versions."""

from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QCheckBox, QComboBox, QSpinBox, QLineEdit, QPushButton, QFileDialog,
    QDialog, QInputDialog, QMessageBox)

from ui.settings.pages.security import _service
from ui.vault.recovery_task import run_recovery_task
from ui.vault.recovery_selection import RecoverySelectionDialog


class RecoverySettingsPage(QScrollArea):
    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.service = _service(dialog)
        self.selected_ids = []
        self.dirty = False
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 16, 12, 20)
        layout.setSpacing(14)
        layout.addWidget(dialog._section_label('Backup & Recovery'))
        self.enabled = QCheckBox('Enable encrypted recovery copies')
        self.enabled.setObjectName('RecoveryEnabled')
        layout.addWidget(self.enabled)
        hint = QLabel('Choose specific items, or Auto Sync to include all current and future Vault items. '
                      'The latest copy updates after changes; the schedule keeps dated versions.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.scope = QComboBox()
        self.scope.addItem('Choose specific items', 'selected')
        self.scope.addItem('All items — Auto Sync', 'all')
        layout.addWidget(self.scope)
        self.choose_items = QPushButton('Choose Vault items…')
        self.selection_status = QLabel()
        layout.addWidget(self.choose_items)
        layout.addWidget(self.selection_status)
        folder = QHBoxLayout()
        self.directory = QLineEdit()
        self.directory.setPlaceholderText('Choose a folder, external drive, or synced folder…')
        browse = QPushButton('Browse…')
        folder.addWidget(self.directory, 1)
        folder.addWidget(browse)
        layout.addLayout(folder)
        form = QFormLayout()
        self.frequency = QComboBox()
        for label, value in [('Daily', 'daily'), ('Weekly', 'weekly'), ('Monthly', 'monthly')]:
            self.frequency.addItem(label, value)
        form.addRow('Keep a dated version:', self.frequency)
        self.retention = QSpinBox()
        self.retention.setRange(1, 100)
        self.retention.setValue(10)
        form.addRow('Copies per version type:', self.retention)
        layout.addLayout(form)
        self.new_password = QLineEdit()
        self.confirm_password = QLineEdit()
        for field in (self.new_password, self.confirm_password):
            field.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password.setPlaceholderText('Backup passphrase (12+ characters; required on first setup)')
        self.confirm_password.setPlaceholderText('Confirm backup passphrase')
        layout.addWidget(self.new_password)
        layout.addWidget(self.confirm_password)
        password_hint = QLabel('Leave both fields empty to keep the current backup passphrase. '
            'Changing it affects future copies; older copies keep their previous passphrase. '
            'Keep it safe: the original Vault is not needed for recovery.')
        password_hint.setWordWrap(True)
        layout.addWidget(password_hint)
        self.state = QLabel()
        self.state.setObjectName('RecoveryStatus')
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        row = QHBoxLayout()
        apply = QPushButton('Apply backup settings')
        backup = QPushButton('Back up now')
        row.addWidget(apply)
        row.addWidget(backup)
        layout.addLayout(row)
        restore = QPushButton('Browse versions / Restore…')
        layout.addWidget(restore)
        note = QLabel('Safety copies are also taken before edits, deletion, password changes, imports, and migrations. '
            'The retention count applies separately to scheduled versions and safety/manual versions, plus the latest copy. '
            'Scheduled work runs while the app and Vault are unlocked; overdue work runs on the next unlock. '
            'Keep a copy on another drive. Apply and Back up now take effect immediately; Cancel will not undo them.')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.setWidget(inner)
        self.load()
        for signal in (self.enabled.toggled, self.scope.currentIndexChanged, self.directory.textChanged,
                       self.frequency.currentIndexChanged, self.retention.valueChanged,
                       self.new_password.textChanged, self.confirm_password.textChanged):
            signal.connect(self.mark_dirty)
        self.scope.currentIndexChanged.connect(self.update_selection)
        self.choose_items.clicked.connect(self.select_items)
        browse.clicked.connect(self.browse)
        apply.clicked.connect(self.apply_settings)
        backup.clicked.connect(self.backup_now)
        restore.clicked.connect(self.restore)

    @property
    def manager(self):
        return self.service.vault.recovery

    def load(self):
        cfg = self.manager.config
        self.enabled.setChecked(cfg.get('enabled', False))
        self.scope.setCurrentIndex(self.scope.findData(cfg.get('scope', 'selected')))
        self.frequency.setCurrentIndex(self.frequency.findData(cfg.get('frequency', 'daily')))
        self.retention.setValue(cfg.get('retention', 10))
        self.directory.setText(cfg.get('directory', ''))
        self.selected_ids = list(cfg.get('selected_ids', []))
        self.update_selection()
        self.refresh_status()
        self.dirty = False

    def mark_dirty(self, *args):
        self.dirty = True

    def update_selection(self, *args):
        all_items = self.scope.currentData() == 'all'
        self.choose_items.setEnabled(not all_items)
        self.selection_status.setText('Includes all items added in the future.' if all_items
                                     else f'{len(self.selected_ids)} item(s) selected; future items require selection.')

    def ensure_unlocked(self):
        from ui.vault.unlock_dialog import VaultUnlockDialog
        from ui.vault.vault_controller import VaultController
        if not self.service.has_master_password():
            QMessageBox.information(self.dialog, 'Password Required', 'Set a Dashboard password in Eclipse first.')
            return False
        parent = self.dialog.parent()
        if self.service.is_locked:
            if parent and hasattr(parent, 'security_controller'):
                if not parent.security_controller.prompt_unlock(self.dialog):
                    return False
            else:
                password, ok = QInputDialog.getText(self.dialog, 'Unlock Dashboard', 'Dashboard password:', QLineEdit.EchoMode.Password)
                if not ok or not self.service.unlock(password):
                    return False
        if self.service.vault.is_unlocked:
            return True
        if parent and hasattr(parent, 'vault_panel'):
            return parent.vault_panel._prompt_unlock()
        controller = VaultController(self.service.vault, parent=self.dialog)
        prompt = VaultUnlockDialog(controller, self.dialog)
        try:
            return prompt.exec() == QDialog.DialogCode.Accepted
        finally:
            controller._idle_timer.stop()
            controller._recovery_timer.stop()
            prompt.deleteLater()
            controller.deleteLater()

    def select_items(self):
        if self.dialog.property('recoveryBusy'):
            return
        if not self.ensure_unlocked():
            return
        prompt = RecoverySelectionDialog(self.service.vault.list_secrets(), self.selected_ids, self.dialog)
        parent = self.dialog.parent()
        if parent and hasattr(parent, 'vault_controller'):
            parent.vault_controller.vault_locked.connect(prompt.reject)
        if prompt.exec() == QDialog.DialogCode.Accepted:
            self.selected_ids = prompt.selected_ids()
            self.update_selection()
            self.mark_dirty()
        prompt.items.clear()
        prompt.deleteLater()

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self.dialog, 'Recovery backup folder', self.directory.text())
        if folder:
            self.directory.setText(folder)

    def apply_settings(self):
        if self.dialog.property('recoveryBusy'):
            return False
        try:
            if not self.enabled.isChecked():
                self.manager.disable()
            else:
                if not self.ensure_unlocked():
                    return False
                password = self.new_password.text()
                if password != self.confirm_password.text():
                    raise ValueError('Backup passphrases do not match.')
                options = dict(directory=self.directory.text(), scope=self.scope.currentData(),
                    selected_ids=list(self.selected_ids), frequency=self.frequency.currentData(),
                    retention=self.retention.value(), password=password or None)
                run_recovery_task(self, 'Saving encrypted recovery settings and the first copy…',
                                  lambda: self.manager.configure(**options))
            self.new_password.clear()
            self.confirm_password.clear()
            self.dirty = False
            self.refresh_status()
            return True
        except Exception as exc:
            QMessageBox.warning(self.dialog, 'Backup Settings Not Saved', str(exc))
            self.refresh_status()
            return False

    def refresh_status(self):
        cfg = self.manager.config
        last = cfg.get('last_success')
        if last:
            last = datetime.fromisoformat(last).astimezone().strftime('%Y-%m-%d %H:%M')
        status = f"Last successful copy: {last or 'None'}\nItems in latest copy: {cfg.get('last_count', 0)}"
        status += '\nAutomatic copies: ' + ('enabled' if self.manager.enabled else 'disabled')
        error = self.manager.error or cfg.get('last_error', '')
        if error:
            status += '\n⚠ ' + error
        try:
            if cfg.get('directory') and Path(cfg['directory']).stat().st_dev == self.manager.path.parent.stat().st_dev:
                status += '\nThis folder is on the same filesystem as the profile. Keep another copy on a separate drive.'
        except OSError:
            pass
        self.state.setText(status)

    def backup_now(self):
        if self.dialog.property('recoveryBusy'):
            return
        if self.dirty and not self.apply_settings():
            return
        if not self.manager.enabled:
            QMessageBox.information(self.dialog, 'Enable Backups', 'Enable and configure recovery copies first.')
            return
        if not self.ensure_unlocked():
            return
        try:
            run_recovery_task(self, 'Creating and verifying an encrypted recovery copy…',
                              lambda: self.manager.snapshot('manual', force_version=True))
            self.refresh_status()
        except Exception as exc:
            QMessageBox.warning(self.dialog, 'Backup Failed', str(exc))

    def restore(self):
        if self.dialog.property('recoveryBusy'):
            return
        from ui.vault.recovery_dialog import RecoveryDialog
        prompt = RecoveryDialog(service=self.service, dashboard=self.dialog.parent(), parent=self.dialog)
        prompt.exec()
        prompt.deleteLater()
        self.load()
