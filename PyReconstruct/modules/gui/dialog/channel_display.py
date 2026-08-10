from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


CHANNEL_COLORS = [
    "red",
    "green",
    "blue",
    "magenta",
    "cyan",
    "yellow",
    "white",
    "orange",
]


class ChannelDisplayDialog(QDialog):

    def __init__(self, parent, n_channels, selected_channels=None, alpha=1.0, apply_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Channels")
        self.n_channels = max(1, int(n_channels))
        self.apply_callback = apply_callback
        self._building = True

        if selected_channels is None:
            selected_channels = list(range(min(3, self.n_channels)))
        selected_channels = [int(c) for c in selected_channels if 0 <= int(c) < self.n_channels]
        if not selected_channels and self.n_channels == 1:
            selected_channels = [0]

        alpha = int(round(max(0.0, min(float(alpha), 1.0)) * 100))

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Select/unselect image channels. One checked channel shows grayscale; multiple checked channels show a composite overlay."))
        layout.addSpacing(8)

        self.channel_checks = []
        grid = QGridLayout()
        for i in range(self.n_channels):
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            cb = QCheckBox(f"Channel {i} ({color})", self)
            cb.setChecked(i in selected_channels)
            cb.stateChanged.connect(self._apply_live)
            self.channel_checks.append(cb)
            grid.addWidget(cb, i // 2, i % 2)
        layout.addLayout(grid)

        button_row = QHBoxLayout()
        select_all = QPushButton("Select all", self)
        clear_all = QPushButton("Clear all", self)
        select_all.clicked.connect(self.selectAllChannels)
        clear_all.clicked.connect(self.clearAllChannels)
        button_row.addWidget(select_all)
        button_row.addWidget(clear_all)
        button_row.addStretch()
        layout.addLayout(button_row)

        slider_row = QHBoxLayout()
        self.alpha_label = QLabel(self)
        self.alpha_slider = QSlider(Qt.Horizontal, self)
        self.alpha_slider.setMinimum(0)
        self.alpha_slider.setMaximum(100)
        self.alpha_slider.setValue(alpha)
        self.alpha_slider.valueChanged.connect(self.updateAlphaLabel)
        self.alpha_slider.valueChanged.connect(self._apply_live)
        slider_row.addWidget(QLabel("Overlay opacity"))
        slider_row.addWidget(self.alpha_slider)
        slider_row.addWidget(self.alpha_label)
        layout.addLayout(slider_row)
        self.updateAlphaLabel()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply_live)
        layout.addWidget(buttons)

        self.setLayout(layout)
        self._building = False

    def selectedChannels(self):
        return [i for i, cb in enumerate(self.channel_checks) if cb.isChecked()]

    def values(self):
        selected = self.selectedChannels()
        alpha = self.alpha_slider.value() / 100.0
        if not selected:
            return "none", 0, "", alpha
        if len(selected) == 1:
            return "single", selected[0], str(selected[0]), alpha
        return "overlay", selected[0], ",".join(str(c) for c in selected), alpha

    def updateAlphaLabel(self):
        self.alpha_label.setText(f"{self.alpha_slider.value()}%")

    def selectAllChannels(self):
        for cb in self.channel_checks:
            cb.setChecked(True)
        self._apply_live()

    def clearAllChannels(self):
        for cb in self.channel_checks:
            cb.setChecked(False)
        self._apply_live()

    def _apply_live(self):
        if self._building:
            return
        if self.apply_callback is not None:
            self.apply_callback(*self.values())

    def accept(self):
        self._apply_live()
        super().accept()

    @staticmethod
    def get(parent, n_channels, selected_channels=None, alpha=1.0, apply_callback=None):
        dialog = ChannelDisplayDialog(parent, n_channels, selected_channels, alpha, apply_callback)
        confirmed = dialog.exec()
        return dialog.values(), bool(confirmed)
