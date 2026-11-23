import sys
from dataclasses import replace

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .engine import SweepEngine


class ReceiverThread(QThread):
    status = Signal(object)
    failed = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.engine = SweepEngine(config, on_status=self.status.emit)

    def run(self):
        try:
            self.engine.run()
        except Exception as error:
            self.failed.emit(str(error))

    def stop(self):
        self.engine.stop()


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.worker = None
        self.closing = False
        self.setWindowTitle("Ghostbox SDR — FM Sweeper")
        self.resize(540, 650)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("GHOSTBOX / SDR")
        title.setStyleSheet("font-size: 25px; font-weight: bold; color: #63dbbd;")
        layout.addWidget(title)
        self.frequency = QLabel("—.——— MHz")
        self.frequency.setStyleSheet("font-size: 42px; font-weight: bold;")
        layout.addWidget(self.frequency)
        self.level = QLabel("Input level: — dBFS (uncalibrated)")
        layout.addWidget(self.level)
        self.settings = QWidget()
        form = QFormLayout(self.settings)

        def number(value, low, high, decimals=0, suffix=""):
            widget = QDoubleSpinBox()
            widget.setDecimals(decimals)
            widget.setRange(low, high)
            widget.setValue(value)
            widget.setSuffix(suffix)
            return widget

        self.start_frequency = number(config.start_mhz, 64, 108, 3, " MHz")
        self.end_frequency = number(config.stop_mhz, 64, 108, 3, " MHz")
        self.step = number(config.step_khz, 25, 2000, 0, " kHz")
        self.dwell = number(config.dwell_ms, 40, 10000, 0, " ms")
        self.settle = number(config.settle_ms, 0, 500, 0, " ms")
        self.direction = QComboBox()
        self.direction.addItems(["forward", "reverse", "random"])
        self.direction.setCurrentText(config.direction)
        self.volume = number(config.volume * 100, 0, 100, 0, " %")
        self.gate = number(config.gate_db, -100, 0, 0, " dBFS")
        self.deemphasis = QComboBox()
        self.deemphasis.addItems(["75", "50"])
        self.deemphasis.setCurrentText(str(config.deemphasis_us))
        self.device = QSpinBox()
        self.device.setRange(0, 99)
        self.device.setValue(config.device)
        self.speech = QCheckBox("300–3400 Hz speech-band filter")
        self.speech.setChecked(config.speech)
        self.demo = QCheckBox("Demo: synthetic tones (no radio)")
        self.demo.setChecked(config.demo)
        self.silent = QCheckBox("Silent: process without playback")
        self.silent.setChecked(config.silent)
        for label, widget in [
            ("Start", self.start_frequency),
            ("End", self.end_frequency),
            ("Channel spacing", self.step),
            ("Audio per channel", self.dwell),
            ("Retune settling", self.settle),
            ("Sweep order", self.direction),
            ("Volume", self.volume),
            ("Noise gate", self.gate),
            ("De-emphasis (µs)", self.deemphasis),
            ("SDR index", self.device),
            ("Audio filtering", self.speech),
            ("Test signal", self.demo),
            ("Playback", self.silent),
        ]:
            form.addRow(label, widget)
        layout.addWidget(self.settings)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start sweep")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_sweep)
        self.stop_button.clicked.connect(self.stop_sweep)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        self.message = QLabel("Ready · Start at low speaker volume.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        note = QLabel(
            "Receive-only experimental radio scanner. Broadcast fragments and noise "
            "are not evidence of paranormal activity. No generated voices or transcription."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #a9b3bf; font-size: 11px;")
        layout.addWidget(note)

    @Slot()
    def start_sweep(self):
        try:
            config = replace(
                self.config,
                start_mhz=self.start_frequency.value(),
                stop_mhz=self.end_frequency.value(),
                step_khz=self.step.value(),
                dwell_ms=int(self.dwell.value()),
                settle_ms=int(self.settle.value()),
                direction=self.direction.currentText(),
                volume=self.volume.value() / 100,
                gate_db=self.gate.value(),
                deemphasis_us=int(self.deemphasis.currentText()),
                device=self.device.value(),
                speech=self.speech.isChecked(),
                demo=self.demo.isChecked(),
                silent=self.silent.isChecked(),
            )
        except ValueError as error:
            self.message.setText(str(error))
            return
        self.worker = ReceiverThread(config, self)
        self.worker.status.connect(self.update_status)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self.finished)
        self.settings.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.message.setText(
            "DEMO · synthetic tones" if config.demo else "Receiving FM · settings locked until Stop"
        )
        self.worker.start()

    @Slot(str)
    def show_error(self, text):
        self.message.setText(f"Error: {text}")

    @Slot(object)
    def update_status(self, status):
        self.frequency.setText(f"{status['frequency'] / 1e6:.3f} MHz")
        if status["level_db"] is not None:
            self.level.setText(f"Input level: {status['level_db']:.1f} dBFS (uncalibrated)")

    @Slot()
    def stop_sweep(self):
        if self.worker:
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.message.setText("Stopping…")

    @Slot()
    def finished(self):
        self.settings.setEnabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.worker.deleteLater()
        self.worker = None
        if not self.message.text().startswith("Error:"):
            self.message.setText("Stopped · change settings and restart to apply.")
        if self.closing:
            self.close()

    def closeEvent(self, event):
        if self.worker is not None:
            self.closing = True
            self.stop_sweep()
            event.ignore()
        else:
            event.accept()


def launch(config):
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(
        "QWidget { background: #17212b; color: #e3eaf0; }"
        "QPushButton { padding: 10px; background: #28524e; border-radius: 4px; }"
        "QPushButton:disabled { background: #26323d; color: #74808a; }"
        "QDoubleSpinBox, QSpinBox, QComboBox { padding: 4px; background: #253340; }"
    )
    window = MainWindow(config)
    window.show()
    return app.exec()
