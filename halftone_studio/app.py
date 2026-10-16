"""絲網印刷半調網點 — 桌面應用程式主視窗。

設計原則：
  - 所有運算交給背景執行緒，介面永不因大圖而凍結
  - 參數拖動即時預覽，並在放開後才做昂貴的完整重算
  - 預覽與匯出分離：預覽縮圖，匯出全解析度
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter,
    QStatusBar, QVBoxLayout, QWidget,
)

from .core import (
    DOT_SHAPES, HalftoneParams, halftone,
)
from .image_io import (
    OUTPUT_FILTER, PREVIEW_MAX_EDGE, ImageError, image_format_of,
    is_lossy_format, load_image, load_image_rgb, save_image,
)
from .preview import PreviewController
from .theme import STYLESHEET
from .widgets import SliderSpin, add_row, build_group

__all__ = ["MainWindow", "main"]

APP_TITLE = "絲網印刷半調網點 Halftone Studio"


class ImageView(QLabel):
    """支援縮放與捲動的影像顯示區。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageView")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 240)
        self._pixmap: QPixmap | None = None
        self._zoom = 1.0
        self._fit = True

    def set_image(self, array: np.ndarray) -> None:
        img = QImage(array.data, array.shape[1], array.shape[0],
                     array.strides[0], QImage.Format_Grayscale8)
        # 保持記憶體有效，QImage 不會自行複製
        img = img.copy()
        self._pixmap = QPixmap.fromImage(img)
        self.update_view()

    def set_rgb(self, array: np.ndarray) -> None:
        """顯示原始彩色影像（已轉為 RGB888）。"""
        rgb = np.ascontiguousarray(array, dtype=np.uint8)
        img = QImage(rgb.data, rgb.shape[1], rgb.shape[0],
                     rgb.strides[0], QImage.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(img)
        self.update_view()

    def clear_image(self) -> None:
        self._pixmap = None
        self.clear()
        self.update_view()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.05, min(16.0, zoom))
        self._fit = False
        self.update_view()

    def zoom(self) -> float:
        return self._zoom

    def fit(self) -> None:
        self._fit = True
        self.update_view()

    def zoom_by(self, factor: float) -> None:
        self.set_zoom(self._zoom * factor)

    def update_view(self) -> None:
        if self._pixmap is None:
            self.setText("尚未載入影像\n\n請點選「開啟 JPG」開始")
            return
        if self._fit:
            m = self.contentsMargins()
            avail_w = max(1, self.width() - m.left() - m.right())
            avail_h = max(1, self.height() - m.top() - m.bottom())
            w, h = self._pixmap.width(), self._pixmap.height()
            s = min(avail_w / w, avail_h / h)
            target = self._pixmap.scaled(
                max(1, int(w * s)), max(1, int(h * s)),
                Qt.KeepAspectRatio, Qt.FastTransformation)
            self.setPixmap(target)
            self._shown = 1.0
            return
        w = int(self._pixmap.width() * self._zoom)
        h = int(self._pixmap.height() * self._zoom)
        self.setPixmap(self._pixmap.scaled(
            max(1, w), max(1, h),
            Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self.update_view()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1360, 880)

        self._gray: np.ndarray | None = None       # 預覽用灰階（縮圖）
        self._full_gray: np.ndarray | None = None  # 全解析度灰階
        self._rgb: np.ndarray | None = None        # 預覽用原始彩色
        self._result: np.ndarray | None = None     # 最近一次預覽輸出
        self._mode = "原圖"                         # 目前預覽模式
        self._source_path: str | None = None
        self._seed = 0

        self._build_ui()
        self._build_menu()

        self.controller = PreviewController(self)
        self.controller.ready.connect(self._on_preview)
        self.controller.failed.connect(self._on_error)
        self.controller.busy_changed.connect(self._on_busy)

        # 拖動滑桿時節流，避免每個像素值都重算
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(60)
        self._debounce.timeout.connect(self._apply_preview)

        self._update_actions()

    # ── 介面建構 ──────────────────────────────────────────
    def _build_ui(self) -> None:
        self.view = ImageView()

        scroll = QScrollArea()
        scroll.setWidget(self.view)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignCenter)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        rl.addWidget(self._build_controls())
        rl.addStretch(1)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(scroll)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([1000, 380])

        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(split)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        hl.addWidget(self.progress)
        self.setCentralWidget(holder)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            "就緒。請開啟 JPG 或 PNG 影像。")

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 檔案
        files, fl = build_group("檔案")
        self.btn_open = QPushButton("開啟 JPG…")
        self.btn_open.clicked.connect(self.on_open)
        self.btn_export = QPushButton("匯出 PNG / JPG…")
        self.btn_export.clicked.connect(self.on_export)
        self.btn_compare = QPushButton("顯示原圖")
        self.btn_compare.clicked.connect(self.on_toggle_compare)
        self.btn_compare.setEnabled(False)
        add_row(fl, "來源", self.btn_open)
        add_row(fl, "對照", self.btn_compare)
        add_row(fl, "輸出", self.btn_export)
        layout.addWidget(files)

        # 網點
        dots, dl = build_group("網點")
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems(DOT_SHAPES)
        self.cmb_shape.currentIndexChanged.connect(self._on_changed)
        add_row(dl, "網點形狀", self.cmb_shape)

        self.sld_freq = SliderSpin(5.0, 200.0, 40.0, 1, 1.0, " lpi")
        self.sld_res = SliderSpin(72.0, 1200.0, 300.0, 0, 10.0, " dpi")
        self.sld_angle = SliderSpin(0.0, 90.0, 45.0, 1, 1.0, " °")
        for w, name in ((self.sld_freq, "網點頻率"),
                        (self.sld_res, "解析度"),
                        (self.sld_angle, "網屏角度")):
            w.changed.connect(self._on_changed)
            add_row(dl, name, w)
        layout.addWidget(dots)

        # 網點外觀
        look, kl = build_group("網點外觀")
        self.sld_stoch = SliderSpin(0.0, 1.0, 0.0, 2, 0.01, "")
        self.sld_grain = SliderSpin(0.1, 8.0, 1.0, 2, 0.05, " ×")
        self.sld_irreg = SliderSpin(0.0, 1.0, 0.0, 2, 0.01, "")
        self.sld_gain = SliderSpin(0.0, 0.6, 0.15, 2, 0.01, "")
        for w, name in ((self.sld_stoch, "隨機網占比"),
                        (self.sld_grain, "顆粒粗細"),
                        (self.sld_irreg, "網點不規則"),
                        (self.sld_gain, "網點擴大")):
            w.changed.connect(self._on_changed)
            add_row(kl, name, w)

        tip = QLabel("隨機網占比 0% = 隨機顆粒，100% = 傳統有序網點")
        tip.setWordWrap(True)
        kl.addWidget(tip)
        layout.addWidget(look)

        # 印刷與隨機
        misc, ml = build_group("印刷與隨機")
        self.sld_min = SliderSpin(0.0, 0.5, 0.03, 2, 0.01, "")
        self.sld_max = SliderSpin(0.5, 1.0, 0.95, 2, 0.01, "")
        self.sld_noise = SliderSpin(8, 128, 64, 0, 4.0, " px")
        for w, name in ((self.sld_min, "最小網點"),
                        (self.sld_max, "最大網點"),
                        (self.sld_noise, "藍雜訊尺寸")):
            w.changed.connect(self._on_changed)
            add_row(ml, name, w)

        seed_row = QWidget()
        seed_layout = QVBoxLayout(seed_row)
        seed_layout.setContentsMargins(0, 0, 0, 0)
        seed_layout.setSpacing(4)

        self.btn_dice = QPushButton("擲新的隨機種子")
        self.btn_dice.clicked.connect(self.on_random_seed)
        seed_layout.addWidget(self.btn_dice)

        add_row(ml, "隨機種子", seed_row)
        layout.addWidget(misc)

        # 檢視
        view, vl = build_group("檢視")
        zoom_row = QWidget()
        zl = QHBoxLayout(zoom_row)
        zl.setContentsMargins(0, 0, 0, 0)
        for text, factor in (("－", 1 / 1.25), ("適應", None),
                             ("＋", 1.25), ("1:1", 1.0)):
            b = QPushButton(text)
            if factor is None:
                b.clicked.connect(self.view.fit)
            elif factor == 1.0:
                b.clicked.connect(lambda: self.view.set_zoom(1.0))
            else:
                b.clicked.connect(lambda f=factor: self.view.zoom_by(f))
            zl.addWidget(b)
        add_row(vl, "縮放", zoom_row)

        self.lbl_size = QLabel("尚未載入影像")
        self.lbl_size.setWordWrap(True)
        vl.addWidget(self.lbl_size)
        layout.addWidget(view)

        return panel

    # ── 功能表 ────────────────────────────────────────────
    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("檔案")
        self.act_open = QAction("開啟 JPG…", self)
        self.act_open.setShortcut("Ctrl+O")
        self.act_open.triggered.connect(self.on_open)
        file_menu.addAction(self.act_open)

        self.act_export = QAction("匯出 PNG / JPG…", self)
        self.act_export.setShortcut("Ctrl+S")
        self.act_export.triggered.connect(self.on_export)
        file_menu.addAction(self.act_export)

        file_menu.addSeparator()
        act_quit = QAction("離開", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = bar.addMenu("檢視")
        act_fit = QAction("適應視窗", self)
        act_fit.setShortcut("Ctrl+0")
        act_fit.triggered.connect(self.view.fit)
        view_menu.addAction(act_fit)

        act_in = QAction("放大", self)
        act_in.setShortcut("Ctrl+=")
        act_in.triggered.connect(lambda: self.view.zoom_by(1.25))
        view_menu.addAction(act_in)

        act_out = QAction("縮小", self)
        act_out.setShortcut("Ctrl+-")
        act_out.triggered.connect(lambda: self.view.zoom_by(1 / 1.25))
        view_menu.addAction(act_out)

        act_reset = QAction("重設為預設參數", self)
        act_reset.triggered.connect(self.on_reset_params)
        view_menu.addAction(act_reset)

        help_menu = bar.addMenu("說明")
        act_about = QAction("關於", self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)

    def _update_actions(self) -> None:
        has = self._gray is not None
        self.act_export.setEnabled(has)
        self.btn_export.setEnabled(has)

    # ── 參數 ──────────────────────────────────────────────
    def _params(self) -> HalftoneParams:
        return HalftoneParams(
            resolution=self.sld_res.value(),
            frequency=self.sld_freq.value(),
            stochastic=self.sld_stoch.value(),
            angle=self.sld_angle.value(),
            dot_shape=self.cmb_shape.currentIndex(),
            shape_amount=self.sld_irreg.value(),
            grain_scale=self.sld_grain.value(),
            noise_size=int(self.sld_noise.value()),
            dot_gain=self.sld_gain.value(),
            min_dot=self.sld_min.value(),
            max_dot=self.sld_max.value(),
            seed=self._seed,
        )

    # ── 事件 ──────────────────────────────────────────────
    def _on_changed(self, *_args) -> None:
        """參數變動：以節流方式更新預覽。"""
        self._debounce.start()

    def _apply_preview(self) -> None:
        if self._gray is None:
            return
        self.controller.request(self._params())

    def _on_preview(self, result: np.ndarray) -> None:
        self._result = result
        self._mode = "網點預覽"
        self.view.set_image(result)
        self._update_compare()

    def on_toggle_compare(self) -> None:
        """在原始彩色影像與網點預覽之間切換，用於對照。"""
        if self._rgb is None:
            return
        if self._mode == "原圖":
            if self._result is not None:
                self.view.set_image(self._result)
                self._mode = "網點預覽"
        else:
            self.view.set_rgb(self._rgb)
            self._mode = "原圖"
        self._update_compare()

    def _update_compare(self) -> None:
        has = self._result is not None and self._rgb is not None
        self.btn_compare.setEnabled(has)
        if not has:
            return
        show_original = self._mode != "原圖"
        self.btn_compare.setText("顯示原圖" if show_original else "顯示網點")

    def _on_error(self, message: str) -> None:
        self.progress.setVisible(False)
        QMessageBox.warning(self, "處理失敗", message)

    def _on_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)

    def on_random_seed(self) -> None:
        self._seed = int(np.random.default_rng().integers(0, 1_000_000))
        self._debounce.start()

    def on_reset_params(self) -> None:
        d = HalftoneParams()
        self.sld_freq.set_value(d.frequency)
        self.sld_res.set_value(d.resolution)
        self.sld_angle.set_value(d.angle)
        self.cmb_shape.setCurrentIndex(d.dot_shape)
        self.sld_stoch.set_value(d.stochastic)
        self.sld_grain.set_value(d.grain_scale)
        self.sld_irreg.set_value(d.shape_amount)
        self.sld_gain.set_value(d.dot_gain)
        self.sld_min.set_value(d.min_dot)
        self.sld_max.set_value(d.max_dot)
        self.sld_noise.set_value(d.noise_size)
        self._seed = d.seed
        self._debounce.start()

    def on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "開啟影像", "", "影像檔 (*.jpg *.jpeg *.png *.JPG *.JPEG)")
        if not path:
            return

        self.progress.setVisible(True)
        QApplication.processEvents()

        name = path.rsplit(chr(92), 1)[-1]
        try:
            # 只讀取可見像素：EXIF 僅用於轉正方向，其餘中繼資料丟棄
            full = load_image(path)
            full_rgb = load_image_rgb(path)
        except ImageError as exc:
            self.progress.setVisible(False)
            QMessageBox.critical(self, "開啟失敗", str(exc))
            return

        small = max(full.shape) > PREVIEW_MAX_EDGE
        try:
            self._gray = (load_image(path, max_edge=PREVIEW_MAX_EDGE)
                          if small else full)
            self._rgb = (load_image_rgb(path, max_edge=PREVIEW_MAX_EDGE)
                         if small else full_rgb)
        except ImageError as exc:
            self.progress.setVisible(False)
            QMessageBox.critical(self, "開啟失敗", str(exc))
            return

        self._source_path = path
        self._full_gray = full
        self._mode = "原圖"

        self.view.set_rgb(self._rgb)
        self.view.fit()
        self.controller.set_gray(self._gray)
        self._update_actions()

        self.setWindowTitle(f"{APP_TITLE} — {name}")
        self.lbl_size.setText(
            f"原始尺寸 {full.shape[1]} × {full.shape[0]} px"
            + (f"\n預覽 {self._gray.shape[1]} × {self._gray.shape[0]} px"
               if small else ""))
        self.progress.setVisible(False)
        self._set_status(f"已載入 {name}（中繼資料已捨棄）")

    def on_export(self) -> None:
        if self._full_gray is None:
            return

        params = self._params()
        errors = params.validate()
        if errors:
            QMessageBox.warning(self, "參數無效", "\n".join(errors))
            return

        base = (self._source_path.rsplit(chr(92), 1)[-1].rsplit(".", 1)[0]
                if self._source_path else "halftone")
        path, _ = QFileDialog.getSaveFileName(
            self, "匯出影像", f"{base}_halftone.png", OUTPUT_FILTER)
        if not path:
            return

        # 副檔名決定格式；未支援的副檔名一律以 PNG 輸出
        fmt = image_format_of(path)
        if not path.lower().endswith((".png", ".jpg", ".jpeg", ".jpe")):
            path = f"{os.path.splitext(path)[0]}.png"
            fmt = "PNG"

        # JPEG 為有損壓縮，二值網點邊緣會出現灰階雜訊，先行確認
        if is_lossy_format(fmt):
            ok = QMessageBox.question(
                self, "確認以 JPEG 輸出",
                "JPEG 是有損壓縮格式，純黑白的網點邊緣在存檔後\n"
                "會出現灰階雜訊，可能影響製版品質。\n\n"
                "程式會以最高畫質輸出以降低失真，但仍有殘留。\n"
                "若要拿來實際製版，建議改用 PNG（無損）。\n\n"
                "仍要以 JPEG 輸出嗎？")
            if ok != QMessageBox.Yes:
                return

        self.progress.setVisible(True)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            result = halftone(self._full_gray, params)
            save_image(result, path)
        except Exception as exc:
            QMessageBox.critical(self, "匯出失敗", str(exc))
            self._set_status("匯出失敗")
        else:
            ink = float((result == 0).mean()) * 100.0
            self._set_status(
                f"已匯出 {path.rsplit(chr(92), 1)[-1]}"
                f"（{result.shape[1]}×{result.shape[0]}，上墨率 {ink:.1f}%）")
            note = ("\n\n注意：JPEG 為有損格式，網點邊緣可能有灰階雜訊。"
                    if is_lossy_format(fmt) else "")
            QMessageBox.information(
                self, "匯出完成",
                f"已另存至：\n{path}\n\n"
                f"格式 {fmt}（不含任何中繼資料）\n"
                f"尺寸 {result.shape[1]} × {result.shape[0]} px\n"
                f"上墨率 {ink:.1f}%{note}")
        finally:
            QApplication.restoreOverrideCursor()
            self.progress.setVisible(False)

    def on_about(self) -> None:
        QMessageBox.about(
            self, "關於",
            f"<b>{APP_TITLE}</b><br><br>"
            "絲網印刷用隨機顆粒半調網點工具。<br>"
            "隨機網占比可連續調整：0% 為藍雜訊隨機顆粒，"
            "100% 為傳統有序網點。<br><br>"
            "純 NumPy 實作，不依賴 GIMP 或其他外部影像軟體。")

    def _set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.controller.shutdown()
        super().closeEvent(event)


def main() -> int:
    QApplication.setAttribute(
        Qt.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Halftone Studio")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()





