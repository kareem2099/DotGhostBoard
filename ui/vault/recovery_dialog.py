"""Recovery remains available even when the original Vault cannot be constructed."""

import json
import hashlib
import tempfile
from datetime import datetime
import os
import subprocess
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QListWidget, QCheckBox, QFileDialog, QMessageBox,
    QScrollArea, QWidget, QFrame, QApplication)

from core import crypto
from core.security.vault.recovery import config_path, load_config
from core.security.vault.recovery_restore import read_recovery, restore_recovery
from core.security.vault.recovery_archive import MAX_ARCHIVE_BYTES, atomic_write
from ui.vault.recovery_task import run_recovery_task


class RecoveryDialog(QDialog):
    def __init__(self, service=None, dashboard=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.dashboard = dashboard
        self.opened_new_profile = False
        self._payload = None
        self._digest = None
        self.setWindowTitle('Vault Recovery')
        self.setMinimumWidth(500)
        self.setMinimumHeight(430)
        screen = QApplication.primaryScreen()
        self.resize(540, min(700, screen.availableGeometry().height() - 80) if screen else 650)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        heading = QLabel('Restore an encrypted recovery copy')
        heading.setStyleSheet('font-size:16px; font-weight:bold;')
        layout.addWidget(heading)
        hint = QLabel('The original Vault has not been reset or deleted. Choose a saved version or a manual .vault backup. '
                      'You need its backup passphrase. Restoring keeps the original Vault files separately.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.versions = QComboBox()
        self._load_versions()
        layout.addWidget(self.versions)
        self.path = QLineEdit()
        self.path.setPlaceholderText('Recovery archive or manual .vault backup')
        browse = QPushButton('Choose backup file…')
        row = QHBoxLayout()
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        self.backup_password = self._password('Backup passphrase')
        layout.addWidget(self.backup_password)
        verify = QPushButton('Verify and preview')
        layout.addWidget(verify)
        self.preview = QListWidget()
        self.preview.setMaximumHeight(130)
        layout.addWidget(self.preview)
        self.new_profile = QCheckBox('Recover into a new profile (original profile stays unchanged)')
        self.new_profile.setChecked(not crypto.has_master_password())
        layout.addWidget(self.new_profile)
        self.profile_folder = QLineEdit()
        self.profile_folder.setPlaceholderText('Empty folder for the recovered profile')
        folder_btn = QPushButton('Choose folder…')
        self.profile_browse = folder_btn
        row = QHBoxLayout()
        row.addWidget(self.profile_folder, 1)
        row.addWidget(folder_btn)
        layout.addLayout(row)
        self.dashboard_password = self._password('Current Dashboard password; create a new one for a new profile')
        self.dashboard_label = QLabel('Dashboard password')
        self.dashboard_confirm = self._password('Confirm new Dashboard password (new profile only)')
        layout.addWidget(self.dashboard_label)
        layout.addWidget(self.dashboard_password)
        layout.addWidget(self.dashboard_confirm)
        self.independent = QCheckBox('Use an independent password for the restored Vault')
        layout.addWidget(self.independent)
        self.vault_password = self._password('New independent Vault password (12+ characters)')
        self.vault_confirm = self._password('Confirm new independent Vault password')
        layout.addWidget(self.vault_password)
        layout.addWidget(self.vault_confirm)
        self.message = QLabel('Backup files are verified before any Vault data is replaced.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        row = QHBoxLayout()
        cancel, restore = QPushButton('Cancel'), QPushButton('Restore verified copy')
        self.restore_button = restore
        self.restore_button.setEnabled(False)
        row.addWidget(cancel)
        row.addWidget(restore)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        outer.addLayout(row)
        self.versions.currentIndexChanged.connect(self._version_selected)
        self.path.textChanged.connect(self._invalidate)
        self.backup_password.textChanged.connect(self._invalidate)
        self.new_profile.toggled.connect(self._update_fields)
        self.independent.toggled.connect(self._update_fields)
        browse.clicked.connect(self._browse)
        folder_btn.clicked.connect(self._choose_folder)
        verify.clicked.connect(self._verify)
        cancel.clicked.connect(self.reject)
        restore.clicked.connect(self._restore)
        self._version_selected()
        self._update_fields()

    @staticmethod
    def _password(hint):
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setPlaceholderText(hint)
        return field

    def _load_versions(self):
        self.versions.addItem('Choose a version or browse a backup file', '')
        try:
            cfg = self.service.vault.recovery.config if self.service else load_config(config_path())
            if not cfg.get('directory'):
                return
            paths = [p for p in Path(cfg['directory']).glob(cfg['profile_id'] + '-*.dgb-recovery')
                     if p.is_file() and not p.is_symlink()]
            for path in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True):
                if path.name.endswith('-latest.dgb-recovery'):
                    label = 'Latest synchronized copy'
                else:
                    try:
                        stamp, reason = path.stem[33:].split('-', 1)
                        date = datetime.strptime(stamp, '%Y%m%dT%H%M%S%fZ').strftime('%Y-%m-%d %H:%M UTC')
                        label = date + ' — ' + reason.replace('-', ' ')
                    except ValueError:
                        label = path.name
                self.versions.addItem(label, str(path))
        except (OSError, ValueError):
            pass  # Browse remains available if settings or the drive are missing.

    def _version_selected(self, *args):
        value = self.versions.currentData()
        if value:
            self.path.setText(value)

    def _update_fields(self, *args):
        self.profile_folder.setEnabled(self.new_profile.isChecked())
        self.profile_browse.setEnabled(self.new_profile.isChecked())
        self.dashboard_label.setText('Create a Dashboard password for the new profile' if self.new_profile.isChecked()
                                     else 'Current Dashboard password')
        self.dashboard_password.setPlaceholderText('Dashboard password (12+ characters for a new profile)')
        self.dashboard_confirm.setVisible(self.new_profile.isChecked())
        self.vault_password.setVisible(self.independent.isChecked())
        self.vault_confirm.setVisible(self.independent.isChecked())

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose encrypted backup', '',
            'Encrypted backups (*.dgb-recovery *.vault);;All files (*)')
        if path:
            self.path.setText(path)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose an empty folder for recovery')
        if folder:
            self.profile_folder.setText(folder)

    def _invalidate(self, *args):
        self._payload = None
        self._digest = None
        self.preview.clear()
        self.restore_button.setEnabled(False)

    def _verify(self):
        if self.property('recoveryBusy'):
            return False
        try:
            path, password = self.path.text(), self.backup_password.text()
            self._payload, self._digest = run_recovery_task(self, 'Decrypting and verifying the backup…',
                lambda: read_recovery(path, password, with_digest=True))
            self.preview.clear()
            self.preview.addItems([item['title'] for item in self._payload['items']])
            self.independent.setChecked(bool(self._payload.get('independent')))
            self.independent.setEnabled(not self._payload.get('independent'))
            self.message.setText(f"Verified: {len(self._payload['items'])} item(s). Review the destination before restoring.")
            self.restore_button.setEnabled(True)
            return True
        except Exception as exc:
            self._invalidate()
            self.message.setText(str(exc))
            return False

    def _restore(self):
        if self.property('recoveryBusy'):
            return
        if self._payload is None and not self._verify():
            return
        root_password = self.dashboard_password.text()
        vault_password = self.vault_password.text() if self.independent.isChecked() else None
        if self.new_profile.isChecked() and (not self.profile_folder.text() or root_password != self.dashboard_confirm.text()):
            self.message.setText('Choose an empty folder and confirm the new Dashboard password.')
            return
        if vault_password is not None and vault_password != self.vault_confirm.text():
            self.message.setText('Vault passwords do not match.')
            return
        if not self.new_profile.isChecked() and not run_recovery_task(self, 'Checking the Dashboard password…',
                lambda: crypto.verify_password(root_password)):
            self.message.setText('Incorrect Dashboard password. You can recover into a new profile if it is unavailable.')
            return
        question = ('Create a recovered profile in the selected empty folder?' if self.new_profile.isChecked() else
                    f"Replace the current Vault with {len(self._payload['items'])} item(s) from this version? The original files will be kept separately. "
                    'Items outside this version will no longer appear in the active Vault. '
                    'Automatic backup settings will need review afterwards.')
        if QMessageBox.question(self, 'Confirm Recovery', question) != QMessageBox.StandardButton.Yes:
            return
        try:
            path, digest = self.path.text(), self._digest
            backup_password = self.backup_password.text()
            new_profile = self.profile_folder.text() if self.new_profile.isChecked() else None
            # A safety checkpoint can update "latest". Freeze the exact encrypted
            # version the user previewed before making that checkpoint.
            with tempfile.TemporaryDirectory(prefix='dotghost-recovery-') as temporary:
                frozen = Path(temporary) / 'verified.backup'
                def prepare():
                    with open(path, 'rb') as stream:
                        data = stream.read(MAX_ARCHIVE_BYTES + 1)
                    if hashlib.sha256(data).hexdigest() != digest:
                        raise ValueError('The backup changed after preview. Verify it again before restoring.')
                    atomic_write(frozen, data)
                    if self.service and not new_profile:
                        try:
                            self.service.vault.recovery.before_change('restore')
                        except ValueError:
                            pass  # Raw originals are preserved even if they cannot be backed up.
                run_recovery_task(self, 'Preserving the verified copy and original Vault…', prepare)
                if self.service and not new_profile:
                    if self.dashboard and hasattr(self.dashboard, 'security_controller'):
                        self.dashboard.security_controller.lock()
                    else:
                        self.service.lock()
                result = run_recovery_task(self, 'Restoring and checking the recovered Vault…',
                    lambda: restore_recovery(frozen, backup_password, root_password,
                        vault_password=vault_password, expected_digest=digest, new_profile=new_profile))
            if self.new_profile.isChecked():
                self._open_profile(result['profile'])
                self.opened_new_profile = True
            elif self.service:
                self.service.vault.reload_after_recovery()
                self.service.unlock(root_password)
                if vault_password:
                    self.service.vault.unlock(vault_password)
                if self.dashboard and hasattr(self.dashboard, 'security_controller'):
                    self.dashboard.security_controller.set_active_key(self.service.active_key)
                if self.dashboard and hasattr(self.dashboard, 'vault_controller'):
                    self.dashboard.vault_controller.on_session_unlocked()
                    self.dashboard.vault_controller.secrets_changed.emit()
            QMessageBox.information(self, 'Recovery Complete', f"Restored {result['count']} item(s). Review backup settings to resume automatic copies.")
            self.accept()
        except Exception as exc:
            self.message.setText('Recovery could not complete: ' + str(exc))

    @staticmethod
    def _open_profile(folder):
        env = dict(os.environ, DOTGHOST_HOME=folder)
        appimage = os.environ.get('APPIMAGE', '')
        if appimage and Path(appimage).is_file() and os.access(appimage, os.X_OK):
            command = [appimage]  # A new AppImage mount survives closing the original profile.
        else:
            command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[2] / 'main.py')]
        subprocess.Popen(command, env=env, start_new_session=True)

    def done(self, result):
        if self.property('recoveryBusy'):
            return
        for field in (self.backup_password, self.dashboard_password, self.dashboard_confirm,
                      self.vault_password, self.vault_confirm):
            field.clear()
        self.preview.clear()
        self._payload = None
        super().done(result)
