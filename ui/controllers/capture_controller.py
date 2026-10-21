"""Keep authenticated background capture separate from access to the Dashboard."""

from PyQt6.QtCore import QObject


class CaptureController(QObject):
    def __init__(self, dashboard):
        super().__init__(dashboard)
        self._dashboard = dashboard
        # This is process-local permission, not a retained decryption key.
        # A cold, locked start still requires successful authentication first.
        self.authorized = not dashboard._is_locked()
        self._history_dirty = False

    def attach(self, watcher):
        watcher.new_text_captured.connect(self._text_captured)
        watcher.new_image_captured.connect(
            lambda *args: self._present("on_image_captured", *args)
        )
        watcher.new_video_captured.connect(
            lambda *args: self._present("on_video_captured", *args)
        )
        watcher.thumb_ready.connect(lambda *args: self._present("on_thumb_ready", *args))
        watcher.primary_fragment_replaced.connect(
            lambda *args: self._present("remove_card", *args)
        )

    def _present(self, method, *args):
        if self._dashboard._is_locked():
            self._history_dirty = True
            return
        getattr(self._dashboard.history_controller, method)(*args)

    def _text_captured(self, item_id, text):
        self._present("on_text_captured", item_id, text)
        # Session locking still stops all network access and outbound sync.
        if not self._dashboard._is_locked():
            self._dashboard.sync_controller.broadcast_text(text)

    def session_changed(self, locked):
        if not locked:
            self.authorized = True
            if self._history_dirty:
                self._dashboard.history_controller.reload()
                self._history_dirty = False
        self.refresh()

    @property
    def ready(self):
        service = self._dashboard.security_service
        return self.authorized and (not service.has_master_password()
                                    or service.vault.recognition_ready)

    def refresh(self):
        watcher = getattr(self._dashboard, "watcher", None)
        if watcher:
            if self.ready and not self._dashboard._is_monitoring_paused:
                watcher.start()
            else:
                watcher.stop()
