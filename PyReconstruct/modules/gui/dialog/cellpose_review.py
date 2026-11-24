"""Preview and explicitly apply Cellpose results. No engine import in the host."""
import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)
from PyReconstruct.modules.backend.view.channel_utils import _array_to_qimage


LAYER_CHOICES = {"DAPI nuclei": "dapi", "Anchor mRNA whole cells": "rna", "Other Cellpose ROIs": "generic"}


def parse_sections(text):
    selected = {}
    for part in text.split(","):
        m = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*", part)
        if not m:
            raise ValueError("Enter section numbers or ranges, for example 1-20 or 1,6,19,40.")
        start, stop = int(m[1]), int(m[2] or m[1])
        if stop < start or stop - start > 99999 or len(selected) > 99999:
            raise ValueError("Use ascending ranges of at most 100,000 sections.")
        selected.update(dict.fromkeys(range(start, stop + 1)))
    return list(selected)


class _Worker(QThread):
    status = Signal(str)
    dispatch = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn, self.result, self.error = fn, None, None

    def run(self):
        try:
            self.result = self.fn(self)
        except Exception as e:
            self.error = e

    def on_ui(self, fn):
        # Synchronous handoff: at most one section's result is queued in memory.
        result = []
        def invoke():
            try:
                result.append((True, fn()))
            except Exception as e:
                result.append((False, e))
        self.dispatch.emit(invoke)
        ok, value = result[0]
        if not ok:
            raise value
        return value


class _Progress(QDialog):
    def __init__(self, parent, title, worker):
        super().__init__(parent)
        self.worker = worker
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        self.label = QLabel(title)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        bar = QProgressBar()
        bar.setRange(0, 0)
        layout.addWidget(bar)
        self.stop = QPushButton("Stop")
        self.stop.clicked.connect(self.reject)
        layout.addWidget(self.stop)
        self.setMinimumWidth(370)
        worker.dispatch.connect(self.invoke, Qt.BlockingQueuedConnection)
        worker.status.connect(self.status)
        worker.finished.connect(self.accept)

    @Slot(object)
    def invoke(self, fn):
        fn()

    @Slot(str)
    def status(self, text):
        if self.stop.isEnabled():
            self.label.setText(text)

    def reject(self):
        self.worker.requestInterruption()
        self.stop.setEnabled(False)
        self.label.setText("Stopping safely. An active prediction may need to finish.")

    def closeEvent(self, event):
        self.reject()
        event.ignore()


def run_task(parent, title, fn):
    worker = _Worker(fn)
    dialog = _Progress(parent, title, worker)
    QTimer.singleShot(0, worker.start)
    dialog.exec()
    worker.wait()
    # Parent-owned Qt dialogs otherwise retain each completed job, its closure and model.
    worker.fn = None
    dialog.setParent(None)
    if worker.error is not None:
        raise worker.error
    return worker.result


class CellposeReview(QDialog):
    def __init__(self, host, options, layer, prefix, boundary=None):
        super().__init__(host)
        self.host, self.options, self.layer = host, options, layer
        self.prefix, self.boundary = prefix, boundary
        self.current = host.series.current_section
        self.session = self.prediction = None
        self.summary = ""
        self.setWindowTitle(f"Review Cellpose-SAM · Section {self.current}")
        layout = QVBoxLayout(self)
        role = next(k for k, v in LAYER_CHOICES.items() if v == layer)
        area = "selected outline" if boundary is not None else "whole section"
        layout.addWidget(QLabel(f"{role}  ·  Channel(s) {', '.join(map(str, options['channels']))}  ·  {area}"))
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setMinimumSize(300, 150)
        layout.addWidget(self.view, 1)
        self.status = QLabel("Preview the current section. Nothing is saved until you click Apply.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        zoom = QPushButton("Actual pixels / fit")
        zoom.clicked.connect(self.toggle_zoom)
        self.actual = False
        form = QFormLayout()
        layout.addLayout(form)
        self.cellprob, self.flow = QDoubleSpinBox(), QDoubleSpinBox()
        self.cellprob.setRange(-20, 20)
        self.flow.setRange(0, 5)
        for spin, default, tip in (
            (self.cellprob, 0., "Lower includes fainter pixels; it can also include background."),
            (self.flow, .4, "Higher tolerates less consistent outlines. Zero disables this filter."),
        ):
            spin.setSingleStep(.1)
            spin.setValue(default)
            spin.setToolTip(tip)
            spin.valueChanged.connect(self.invalidate)
        row = QHBoxLayout()
        row.addWidget(QLabel("Cell threshold"))
        row.addWidget(self.cellprob)
        row.addWidget(QLabel("Flow threshold"))
        row.addWidget(self.flow)
        row.addStretch()
        row.addWidget(zoom)
        form.addRow(row)
        self.targets = QLineEdit(str(self.current))
        self.targets.setPlaceholderText("e.g. 1-20 or 1,6,19,40")
        self.targets.setEnabled(boundary is None)
        self.targets.setToolTip("An outline belongs only to the current section." if boundary is not None
                                else "Use the same channel indexes on every selected section.")
        form.addRow("Apply to sections", self.targets)
        self.skip = QCheckBox("Skip sections that already have ROIs in this layer")
        self.skip.setChecked(True)
        layout.addWidget(self.skip)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        self.refresh = QPushButton("Preview")
        self.refresh.clicked.connect(self.preview)
        self.apply_button = QPushButton("Apply to sections")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_results)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for button in (self.refresh, self.apply_button, close):
            button.setMinimumHeight(36)
            buttons.addWidget(button)
        self.resize(720, 580)
        self.initial_timer = QTimer(self)
        self.initial_timer.setSingleShot(True)
        self.initial_timer.timeout.connect(self.initial_preview)
        self.first_show = True

    def showEvent(self, event):
        super().showEvent(event)
        if self.first_show:
            self.first_show = False
            self.initial_timer.start(0)

    def initial_preview(self):
        if self.isVisible():
            self.preview()

    def toggle_zoom(self):
        self.actual = not self.actual
        if self.actual:
            self.view.resetTransform()
        else:
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def done(self, result):
        super().done(result)
        self.session = self.prediction = None
        self.scene.clear()

    def invalidate(self):
        self.prediction = None
        self.apply_button.setEnabled(False)
        self.scene.clear()
        self.status.setText("Settings changed. Click Preview to see the new contours before applying.")

    def thresholds(self):
        return dict(cellprob_threshold=self.cellprob.value(), flow_threshold=self.flow.value())

    def preview(self):
        thresholds = self.thresholds()
        section = self.host.field.section
        self.invalidate()
        def compute(worker):
            if self.session is None:
                from pyrecon_connector import create_cellpose_session
                self.session = create_cellpose_session(**self.options)
            result = self.session.predict(section, boundary_trace=self.boundary, **thresholds)
            return None if worker.isInterruptionRequested() else result
        try:
            result = run_task(self, f"Predicting section {self.current}…", compute)
        except Exception as e:
            self.status.setText(f"Preview failed: {e}")
            return
        if result is None:
            self.status.setText("Preview stopped. No ROIs were saved.")
            return
        self.prediction = result
        pix = self.scene.addPixmap(QPixmap.fromImage(_array_to_qimage(result.preview)))
        result.preview = None  # The scene owns the display pixels; Apply only needs the contours.
        self.scene.setSceneRect(pix.boundingRect())
        if not self.actual:
            self.view.fitInView(pix, Qt.KeepAspectRatio)
        self.apply_button.setEnabled(True)
        text = f"Section {self.current}: {len(result.contours)} predicted ROIs in cyan. Nothing saved yet."
        try:
            if self.session.existing(section, self.layer):
                text += " This section already has ROIs in this layer and will be skipped by default."
        except ValueError as e:
            text += f" Layer needs review: {e}"
        self.status.setText(text)

    def apply_results(self):
        if self.prediction is None:
            return
        try:
            numbers = parse_sections(self.targets.text())
        except ValueError as e:
            self.status.setText(str(e))
            return
        if self.boundary is not None and numbers != [self.current]:
            self.status.setText("A selected outline can only be applied to its original section.")
            return
        skip = self.skip.isChecked()
        if not skip and QMessageBox.question(self, "Append ROIs?",
                "Existing ROIs will be kept. Appending can create overlapping duplicates. Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.summary = self._batch(numbers, skip, self.thresholds())
        self.accept()

    def _batch(self, numbers, skip, thresholds):
        host, session = self.host, self.session
        states = host.field.series_states
        counts, skipped = {}, []
        def save(section, prediction):
            if not prediction.contours:
                return 0
            if not any(counts.values()):
                states.addState()
            section_state = states[section]
            n = session.apply(section, prediction, self.layer, prefix=self.prefix)
            section_state.addState(section, host.series)
            states.addSectionUndo(section.n)
            section.save()
            return n
        def work(worker):
            for i, number in enumerate(numbers, 1):
                if worker.isInterruptionRequested():
                    return True
                worker.status.emit(f"Section {number} ({i} of {len(numbers)})…")
                if number not in host.series.sections:
                    skipped.append(f"{number}: missing section")
                    continue
                try:
                    section = host.series.loadSection(number)
                    if skip and session.existing(section, self.layer):
                        skipped.append(f"{number}: layer already has ROIs")
                        continue
                    if not Path(section.src_fp).exists():
                        skipped.append(f"{number}: image not found")
                        continue
                    pred = self.prediction if number == self.current else session.predict(section, preview=False, **thresholds)
                except (FileNotFoundError, ValueError) as e:
                    skipped.append(f"{number}: {e}")
                    continue
                if worker.isInterruptionRequested():
                    return True
                counts[number] = worker.on_ui(lambda: save(section, pred))
            return False
        try:
            stopped = run_task(self, "Applying reviewed Cellpose settings", work)
            title = "Stopped." if stopped else "Finished."
        except Exception as e:
            title = f"Stopped on error: {e}."
        finally:
            if any(counts.values()):
                host.series.save()
                host.field.reload()
                host.field.table_manager.recreateTables()
                host.seriesModified(True)
        report = f"{title} Created {sum(counts.values())} ROIs across {len(counts)} processed section(s)."
        if skipped:
            report += f" Skipped {len(skipped)}.\n" + "\n".join(skipped)
        return report
