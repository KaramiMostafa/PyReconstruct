"""File-based EM registration and result review; all computation is in the connector."""

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .helper import BrowseWidget


class RegistrationWorker(QThread):
    progress = Signal(int, str)
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, parent, options):
        super().__init__(parent)
        self.options = options

    def run(self):
        try:
            from pyrecon_connector import run_em_registration
            result = run_em_registration(
                **self.options, progress=self.progress.emit,
                cancelled=self.isInterruptionRequested,
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class EMRegistrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registration — EM images, masks, and landmarks")
        self.resize(850, 780)
        self.worker = None
        self.result = None
        self.close_when_finished = False
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Register a moving EM image and its mask to a fixed EM image using matching "
            "landmark IDs. Thin-plate splines can deform geometry. Results are saved as "
            "a new dataset; open its images folder as a new series after review."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.form_widget = QWidget()
        form = QFormLayout(self.form_widget)
        self.fields = {}
        for key, title, kind in (
            ("fixed_image", "Fixed/reference EM TIFF", "file"),
            ("fixed_mask", "Fixed mask TIFF (optional pair)", "file"),
            ("moving_image", "Moving EM TIFF", "file"),
            ("moving_mask", "Moving mask TIFF (optional pair)", "file"),
            ("landmarks_csv", "Landmark coordinates CSV", "file"),
            ("output_dir", "Output parent folder", "dir"),
        ):
            file_filter = "CSV files (*.csv)" if key == "landmarks_csv" else "TIFF files (*.tif *.tiff)"
            field = BrowseWidget(self, type=kind, filter=file_filter)
            form.addRow(title, field)
            self.fields[key] = field
        self.fixed_section, self.moving_section = QSpinBox(), QSpinBox()
        for widget, value in ((self.fixed_section, 1), (self.moving_section, 2)):
            widget.setRange(0, 1000000)
            widget.setValue(value)
        form.addRow("Fixed slice number in CSV", self.fixed_section)
        form.addRow("Moving slice number in CSV", self.moving_section)
        self.origin = QComboBox()
        self.origin.addItem("Top-left (image/Fiji pixel coordinates)", "top-left")
        self.origin.addItem("Bottom-left (pixel coordinates only)", "bottom-left")
        self.pixel_base = QComboBox()
        self.pixel_base.addItem("Zero-based: first pixel is 0", 0)
        self.pixel_base.addItem("One-based: first pixel is 1", 1)
        form.addRow("Coordinate origin", self.origin)
        form.addRow("Coordinate indexing", self.pixel_base)
        help_text = QLabel(
            "CSV: point,slice,X,Y (including the supplied unnamed point column), or "
            "point,fixed_x,fixed_y,moving_x,moving_y. Use at least 3 non-collinear "
            "shared points; spread more landmarks across the image where possible. "
            "Coordinates must refer to raw TIFF pixels, not PyReconstruct's transformed "
            "micrometre coordinates. Supply both masks or neither. Masks must match "
            "their image sizes and contain integer labels (0 = background); they are "
            "warped using the landmarks, not used to estimate the transform."
        )
        help_text.setWordWrap(True)
        form.addRow(help_text)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form_widget)
        layout.addWidget(scroll, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.status = QLabel("Choose inputs and an output folder, then run registration.")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.preview)
        buttons = QHBoxLayout()
        self.run_button = QPushButton("Run registration")
        self.open_button = QPushButton("Open results folder")
        self.open_button.setEnabled(False)
        self.close_button = QPushButton("Close")
        self.run_button.clicked.connect(self.start_registration)
        self.open_button.clicked.connect(self.open_results)
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.open_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def options(self):
        options = {key: widget.text().strip() for key, widget in self.fields.items()}
        for key in ("fixed_image", "moving_image", "landmarks_csv"):
            if not options[key] or not Path(options[key]).is_file():
                raise ValueError(f"Choose an existing {key.replace('_', ' ')} file.")
        if not options["output_dir"] or not Path(options["output_dir"]).is_dir():
            raise ValueError("Choose an existing output parent folder.")
        if bool(options["fixed_mask"]) != bool(options["moving_mask"]):
            raise ValueError("Select both masks, or leave both blank.")
        options.update(
            fixed_section=self.fixed_section.value(), moving_section=self.moving_section.value(),
            coordinate_origin=self.origin.currentData(), coordinate_base=self.pixel_base.currentData(),
        )
        if options["fixed_section"] == options["moving_section"]:
            raise ValueError("Fixed and moving slice numbers must be different.")
        return options

    def start_registration(self):
        if self.worker is not None:
            return
        try:
            options = self.options()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.result = None
        self.preview.clear()
        self.open_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.form_widget.setEnabled(False)
        self.close_button.setText("Cancel run")
        self.progress_bar.setValue(0)
        self.status.setText("Starting registration...")
        self.worker = RegistrationWorker(self, options)
        self.worker.progress.connect(self.update_progress)
        self.worker.result_ready.connect(self.show_result)
        self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(self.registration_finished)
        self.worker.start()

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status.setText(message)

    def show_result(self, result):
        self.result = result
        report = result["report"]
        self.status.setText(
            f"Saved to {result['output_dir']}\n"
            f"Shared landmarks: {len(report['point_ids'])}; "
            f"uncovered canvas: {report['outside_moving_fraction']:.1%}. "
            "Review preview.png and registration.json before using the result. "
            "Use the fixed image's pixel size when importing the images folder as a new series. "
            "Small landmark fit errors alone do not validate registration accuracy."
        )
        self.preview.setPixmap(QPixmap(result["files"]["preview"]).scaled(
            810, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        ))
        self.open_button.setEnabled(True)

    def registration_finished(self):
        self.worker.wait()
        self.worker.deleteLater()
        self.worker = None
        self.run_button.setEnabled(True)
        self.form_widget.setEnabled(True)
        self.close_button.setText("Close")
        if self.close_when_finished:
            super().reject()

    def reject(self):
        if self.worker is not None:
            self.close_when_finished = True
            self.worker.requestInterruption()
            self.status.setText("Cancelling after the current processing block...")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

    def open_results(self):
        if self.result is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.result["output_dir"]))
