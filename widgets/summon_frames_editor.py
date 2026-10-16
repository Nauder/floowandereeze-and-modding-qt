"""GIF/MP4/PNG import controls with asynchronous preparation and frame playback."""

from bisect import bisect_right

from PySide6 import QtCore, QtGui, QtWidgets

from unity.summon_frames import FrameOptions


class SummonFramesEditor(QtWidgets.QWidget):
    """Prepared preview pixels are also the pixels used by the writer."""

    applied = QtCore.Signal(object)
    busy_changed = QtCore.Signal(bool)

    def __init__(
        self,
        service,
        rows,
        parent=None,
        *,
        source=None,
        lower_quality=False,
        card_name="Selected card",
    ):
        super().__init__(parent)
        self.service, self.rows = service, list(rows)
        self.lower_quality = bool(lower_quality)
        self.card_name = card_name
        self.plan = None
        self.worker = None
        self._memory_warning = None
        self._retry_import = None
        self.pixmaps = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        notice = self.notice = QtWidgets.QLabel(
            "Original files are backed up automatically."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        source_row = QtWidgets.QHBoxLayout()
        self.source = QtWidgets.QLineEdit()
        self.source.setAcceptDrops(False)
        self.source.setPlaceholderText(
            "GIF/MP4 file or folder containing numbered PNG frames"
        )
        source_row.addWidget(self.source, 1)
        self.gif_button = QtWidgets.QPushButton("Choose GIF / MP4…")
        self.png_button = QtWidgets.QPushButton("PNG folder…")
        source_row.addWidget(self.gif_button)
        source_row.addWidget(self.png_button)
        layout.addLayout(source_row)
        form = QtWidgets.QGridLayout()
        self.controls = {}
        numeric = (
            ("fps", "Output FPS", 1, 60, 30),
            ("png_fps", "PNG source FPS", 1, 60, 30),
            ("edge", "Frame resolution (long edge)", 32, 1024, 256),
            ("size", "Size (%)", 10, 200, 100),
            ("x", "Horizontal offset (%)", -100, 100, 0),
            ("y", "Vertical offset (%)", -100, 100, 0),
        )
        for index, (name, label, low, high, value) in enumerate(numeric):
            spin = QtWidgets.QSpinBox()
            spin.setRange(low, high)
            spin.setValue(value)
            self.controls[name] = spin
            row, column = divmod(index, 2)
            form.addWidget(QtWidgets.QLabel(label), row, column * 2)
            form.addWidget(spin, row, column * 2 + 1)
            spin.valueChanged.connect(self.invalidate)
        for index, (name, label, choices) in enumerate(
            (
                (
                    "framing",
                    "Framing",
                    (("Fit with transparent padding", "fit"), ("Crop to fill", "crop")),
                ),
                (
                    "timing",
                    "Timing",
                    (
                        ("Fit source to summon duration", "fit"),
                        ("Keep speed; trim / hold last frame", "source"),
                    ),
                ),
            )
        ):
            combo = QtWidgets.QComboBox()
            for text, value in choices:
                combo.addItem(text, value)
            self.controls[name] = combo
            form.addWidget(QtWidgets.QLabel(label), 3 + index, 0)
            form.addWidget(combo, 3 + index, 1, 1, 3)
            combo.currentIndexChanged.connect(self.invalidate)
        self.settings_toggle = QtWidgets.QCheckBox("Adjust timing, size and position")
        self.settings_toggle.setStyleSheet(
            "QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #8292aa; border-radius: 2px; background: #111721; } QCheckBox::indicator:checked { background: #15a06f; border-color: #15a06f; }"
        )
        self.settings_box = QtWidgets.QGroupBox("Animation settings")
        self.settings_box.setLayout(form)
        self.settings_box.setVisible(False)
        self.settings_toggle.toggled.connect(self.settings_box.setVisible)
        layout.addWidget(self.settings_toggle)
        layout.addWidget(self.settings_box)
        self.preview = QtWidgets.QLabel("Choose input and generate a preview.")
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(240, 120)
        self.preview.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Ignored
        )
        self.preview.setStyleSheet(
            "background: #242830; color: #e1e4ea; border: 1px solid #586070;"
        )
        layout.addWidget(self.preview, 1)
        playback = QtWidgets.QHBoxLayout()
        self.play = QtWidgets.QPushButton("Play")
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.time_label = QtWidgets.QLabel("0.000 s")
        playback.addWidget(self.play)
        playback.addWidget(self.slider, 1)
        playback.addWidget(self.time_label)
        layout.addLayout(playback)
        self.status = QtWidgets.QLabel(
            "GIF and MP4 timing is respected. "
            "PNG files use natural filename order (1, 2, 10)."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QtWidgets.QHBoxLayout()
        self.generate = QtWidgets.QPushButton("Update preview")
        self.apply = QtWidgets.QPushButton("Replace animation")
        buttons.addWidget(self.generate)
        buttons.addStretch()
        buttons.addWidget(self.apply)
        layout.addLayout(buttons)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(16)
        self.elapsed = QtCore.QElapsedTimer()
        self.play_offset = 0
        self.timer.timeout.connect(self.tick)
        self.play.clicked.connect(self.toggle_play)
        self.slider.valueChanged.connect(self.show_frame)
        self.slider.sliderPressed.connect(self.pause)
        self.source.textChanged.connect(self.invalidate)
        self.gif_button.clicked.connect(self.choose_gif)
        self.png_button.clicked.connect(self.choose_pngs)
        self.generate.clicked.connect(self.prepare)
        self.apply.clicked.connect(self.apply_plan)
        self.invalidate()
        if source:
            self.use_source(source)

    def set_target(self, service, rows, card_name, lower_quality):
        """Retarget retained input only when the previous worker has finished."""
        if self.worker is not None:
            return
        self.service, self.rows = service, list(rows)
        self.card_name, self.lower_quality = card_name, bool(lower_quality)
        self.invalidate()
        self.notice.setText("Original files are backed up automatically.")
        self.set_controls(True)
        if service is not None and self.rows and self.source.text().strip():
            QtCore.QTimer.singleShot(0, self.prepare)

    def use_source(self, source):
        """Use a picked or dropped input and prepare it automatically."""
        if self.worker is not None:
            return
        self.source.setText(str(source))
        QtCore.QTimer.singleShot(0, self.prepare)

    def options(self):
        return FrameOptions(
            **{
                name: (
                    widget.currentData()
                    if isinstance(widget, QtWidgets.QComboBox)
                    else widget.value()
                )
                for name, widget in self.controls.items()
            }
        )

    def invalidate(self, *_):
        self.pause()
        self.plan = None
        self.pixmaps = []
        self.apply.setEnabled(False)
        self.play.setEnabled(False)
        self.slider.setEnabled(False)
        self.preview.setText("Generate a preview with the current settings.")

    def choose_gif(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose GIF or MP4",
            "",
            "Animations (*.gif *.mp4);;GIF files (*.gif);;MP4 files (*.mp4)",
        )
        if path:
            self.use_source(path)

    def choose_pngs(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose numbered PNG frames folder"
        )
        if path:
            self.use_source(path)

    def start(self, callback, success):
        # Import here avoids an import cycle with the owning page.
        from pages.summon_animation import _Worker

        if self.worker is not None:
            return
        self.pause()
        self.set_controls(False)
        self.status.setText("Working…")
        self.worker = _Worker(callback, self)
        self.worker.completed.connect(success)
        self.worker.failed.connect(self.failed)
        self.worker.memory_warning.connect(self._memory_approval_needed)
        self.worker.finished.connect(self.worker_finished)
        self.busy_changed.emit(True)
        self.worker.start()

    def set_controls(self, enabled):
        for widget in [
            self.source,
            self.gif_button,
            self.png_button,
            self.generate,
            self.settings_toggle,
            *self.controls.values(),
        ]:
            widget.setEnabled(enabled)
        ready = enabled and self.service is not None and bool(self.rows)
        self.gif_button.setEnabled(ready)
        self.png_button.setEnabled(ready)
        self.generate.setEnabled(ready)
        self.apply.setEnabled(enabled and self.plan is not None)
        self.play.setEnabled(enabled and self.plan is not None)
        self.slider.setEnabled(enabled and self.plan is not None)

    def worker_finished(self):
        worker = self.worker
        retry = self._retry_import
        self._retry_import = None
        approved = False
        if self._memory_warning is not None:
            message = self._memory_warning
            self._memory_warning = None
            answer = QtWidgets.QMessageBox.warning(
                self,
                "Large animation import",
                message,
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            approved = answer == QtWidgets.QMessageBox.StandardButton.Yes
            if not approved:
                self.status.setText(
                    "Import cancelled. Choose a smaller source or retry."
                )
        self.worker = None
        if worker:
            worker.deleteLater()
        if approved:
            self.start(retry, self.prepared)
            return
        self.set_controls(True)
        self.busy_changed.emit(False)

    def _memory_approval_needed(self, message):
        self._memory_warning = message

    def failed(self, message):
        self.invalidate()
        self.status.setText("Import failed: " + message)

    def prepare(self):
        if self.worker is not None:
            return
        self.invalidate()
        if self.service is None or not self.rows:
            self.status.setText("Select a card and configure your game path first.")
            return
        if not self.source.text().strip():
            self.status.setText("Choose a GIF, MP4 or PNG folder first.")
            return
        source, options = self.source.text().strip(), self.options()
        service, rows = self.service, list(self.rows)
        lower_quality = self.lower_quality
        self._retry_import = lambda: service.prepare_frame_animation(
            rows,
            source,
            options,
            lower_quality=lower_quality,
            allow_large_import=True,
        )
        self.start(
            lambda: service.prepare_frame_animation(
                rows, source, options, lower_quality=lower_quality
            ),
            self.prepared,
        )

    def prepared(self, plan):
        self.plan = plan
        self.pixmaps = []
        for payload in plan["preview"]:
            pixmap = QtGui.QPixmap()
            if not pixmap.loadFromData(payload):
                self.failed("Preview image could not be decoded.")
                return
            self.pixmaps.append(pixmap)
        self.slider.setRange(0, len(plan["times"]) - 1)
        self.slider.setValue(0)
        self.notice.setText(
            plan.get("quality_warning") or "Original files are backed up automatically."
        )
        self.status.setText(
            plan["summary"] + f" · Source: {plan['source_duration']:.3f} s"
        )
        self.show_frame(0)

    def show_frame(self, index):
        if self.plan is None:
            return
        pixmap = self.pixmaps[self.plan["indices"][index]]
        options = self.plan["options"]
        # Display original framing bounds, including size/position adjustments.
        width, height = max(1, self.preview.width() - 24), max(
            1, self.preview.height() - 24
        )
        scale = min((width - 2) / pixmap.width(), (height - 2) / pixmap.height())
        box_w, box_h = pixmap.width() * scale, pixmap.height() * scale
        canvas = QtGui.QPixmap(width, height)
        canvas.fill(QtGui.QColor("#242830"))
        painter = QtGui.QPainter(canvas)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        box_x, box_y = (width - box_w) / 2, (height - box_h) / 2
        painter.setPen(QtGui.QColor("#8292aa"))
        painter.drawRect(QtCore.QRectF(box_x, box_y, box_w, box_h))
        image_w, image_h = box_w * options.size / 100, box_h * options.size / 100
        painter.drawPixmap(
            QtCore.QRectF(
                box_x + (box_w - image_w) / 2 + box_w * options.x / 100,
                box_y + (box_h - image_h) / 2 - box_h * options.y / 100,
                image_w,
                image_h,
            ),
            pixmap,
            QtCore.QRectF(pixmap.rect()),
        )
        painter.end()
        self.preview.setPixmap(canvas)
        self.time_label.setText(f"{self.plan['times'][index]:.3f} s")

    def pause(self):
        self.timer.stop()
        self.play.setText("Play")

    def toggle_play(self):
        if self.plan is None:
            return
        if self.timer.isActive():
            self.pause()
        else:
            self.play_offset = self.plan["times"][self.slider.value()]
            self.elapsed.start()
            self.timer.start()
            self.play.setText("Pause")

    def tick(self):
        if self.plan is None:
            self.pause()
            return
        time = (self.play_offset + self.elapsed.elapsed() / 1000) % self.plan[
            "duration"
        ]
        self.slider.setValue(max(0, bisect_right(self.plan["times"], time) - 1))

    def apply_plan(self):
        if self.plan is None or self.worker is not None:
            return
        self.pause()
        affected = self.plan["affected"]
        quality = "lower-quality" if self.lower_quality else "high-quality"
        card_ids = {r["card_id"] for r in self.rows}
        shared = sorted(
            {
                r["display_name"] or f"Card {r['card_id']}"
                for r in affected
                if r["card_id"] is not None and r["card_id"] not in card_ids
            }
        )
        message = (
            f"Close Master Duel first. Replace the {quality} animation for {self.card_name}?\n"
            "Original files are backed up automatically."
        )
        if self.plan.get("quality_warning"):
            message += "\n" + self.plan["quality_warning"]
        if shared:
            message += "\nThese cards share affected files: " + ", ".join(shared)
        answer = QtWidgets.QMessageBox.question(
            self,
            "Replace summon animation",
            message,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        plan = self.plan
        self.start(lambda: self.service.apply_frame_animation(plan), self.changed)

    def changed(self, result):
        self.applied.emit(result)
        self.plan = None
        self.pixmaps = []
        self.status.setText(
            "Replacement applied; original backups retained. Verify the summon in-game."
        )
        self.preview.setText("Replacement applied.")

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
            return
        self.pause()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.plan is not None:
            self.show_frame(self.slider.value())
