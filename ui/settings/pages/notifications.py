"""Desktop notification preferences and a preview using the native transport."""

from PyQt6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget


def build_notifications_tab(dialog):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(16, 20, 16, 16)
    layout.setSpacing(14)
    layout.addWidget(dialog._section_label("Desktop notifications"))

    dialog._notifications_enabled = QCheckBox("Enable desktop notifications")
    dialog._notifications_enabled.setChecked(
        dialog._settings.get("notifications_enabled", True)
    )
    layout.addWidget(dialog._notifications_enabled)
    hint = QLabel(
        "Apply changes with Save. Secret protection and in-app review prompts stay active."
    )
    hint.setWordWrap(True)
    layout.addWidget(hint)
    layout.addWidget(dialog._hsep())

    dialog._notifications_security = QCheckBox("Security alerts")
    dialog._notifications_updates = QCheckBox("Available updates")
    dialog._notification_sound = QCheckBox("Allow notification sounds")
    options = [
        (dialog._notifications_security, "notifications_security"),
        (dialog._notifications_updates, "notifications_updates"),
        (dialog._notification_sound, "notification_sound_enabled"),
    ]
    for checkbox, key in options:
        checkbox.setChecked(dialog._settings.get(key, True))
        layout.addWidget(checkbox)
    dialog._notification_sound.setToolTip(
        "Uses your desktop's notification sound preferences where supported.\n"
        "Independent of clipboard capture sounds in General."
    )
    privacy = QLabel("Notification previews never include passwords or Vault item names.")
    privacy.setWordWrap(True)
    layout.addWidget(privacy)

    test_button = QPushButton("Test notification")
    test_button.setObjectName("TestNotificationBtn")
    status = QLabel()
    status.setWordWrap(True)
    status.setObjectName("NotificationTestStatus")
    layout.addWidget(test_button)
    layout.addWidget(status)

    def update_enabled(enabled):
        for checkbox, _ in options:
            checkbox.setEnabled(enabled)
        test_button.setEnabled(enabled)

    def test_notification():
        from core.notifications import send_desktop_notification

        status.setText("Testing…")

        def result(delivered):
            status.setText(
                "Sent to your desktop. If it is hidden, check Do Not Disturb."
                if delivered else "Desktop notifications are unavailable in this session."
            )

        queued = send_desktop_notification(
            "DotGhostBoard", "Desktop notifications are enabled.",
            sound=dialog._notification_sound.isChecked(), on_result=result,
        )
        if not queued:
            result(False)

    dialog._notifications_enabled.toggled.connect(update_enabled)
    test_button.clicked.connect(test_notification)
    update_enabled(dialog._notifications_enabled.isChecked())
    layout.addStretch()
    return page
