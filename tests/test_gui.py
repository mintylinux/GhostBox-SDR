import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ghostbox_sdr.engine import SweepConfig  # noqa: E402
from ghostbox_sdr.gui import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    yield instance
    instance.processEvents()


def pump_until(app, condition, seconds=4):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert condition()


def test_desktop_start_stop_and_close(app):
    window = MainWindow(SweepConfig(demo=True, silent=True))
    window.show()
    try:
        window.start_sweep()
        assert not window.start_button.isEnabled()
        pump_until(app, lambda: window.frequency.text() != "—.——— MHz")
        window.stop_sweep()
        pump_until(app, lambda: window.worker is None)
        assert window.start_button.isEnabled()
        window.start_sweep()
        window.close()
        pump_until(app, lambda: window.worker is None and not window.isVisible())
    finally:
        if window.worker is not None:
            window.worker.stop()
            window.worker.wait(5000)
            app.processEvents()
        window.close()


def test_desktop_rejects_reversed_range(app):
    window = MainWindow(SweepConfig(demo=True, silent=True))
    window.start_frequency.setValue(108)
    window.end_frequency.setValue(88)
    window.start_sweep()
    assert window.worker is None
    assert "FM range" in window.message.text()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
