"""絲網印刷半調墨點 — 桌面應用程式主視窗。

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
from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction, QBrush, QColor, QImage, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter,
    QStatusBar, QVBoxLayout, QWidget,
)

from .core import (
    DOT_SHAPES, HalftoneParams, halftone, physical_metrics,
)
from .detail import DetailPane, DetailWindow
from .image_io import (
    OUTPUT_FILTER, PREVIEW_MAX_EDGE, ImageError, image_format_of,
    is_lossy_format, load_image, load_image_rgb,
)
from .icons import app_icon
from .preview import ExportController, PreviewController
from .theme import get_stylesheet
from .widgets import InkRange, SliderSpin, add_row, build_group

__all__ = ["MainWindow", "main"]

APP_TITLE = "絲網印刷半調墨點 Halftone Studio"

# 控制面板的寬度範圍。設定上下限可避免面板被拉伸得過寬，
# 或在視窗較窄時被擠壓而顯示不全。
PANEL_MIN_WIDTH = 360
PANEL_MAX_WIDTH = 420

# 總覽區的最小尺寸（置合模式使用）
MIN_VIEW_W = 320
MIN_VIEW_H = 240


class ImageView(QLabel):
    """支援縮放與捲動的影像顯示區。

    影像由 paintEvent 自己繪製，不交給 QLabel 畫。原因是 QLabel 在
    圖片大於控件時會**自行再縮放一次**，而 self.pixmap() 回傳的仍是
    縮放前的原圖 —— 畫面位置、框線位置與點擊換算於是各用各的座標，
    三者對不上。實測框線明顯偏移。

    現在統一由 _drawn（影像在控件內的實際矩形）這一個來源換算，
    繪製、框線、點擊三者必然一致。
    """

    # 使用者在總覽圖上點擊（影像座標）
    crop_clicked = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageView")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 240)
        self._pixmap: QPixmap | None = None
        self._scaled: QPixmap | None = None
        self._crop: tuple[int, int, int, int] | None = None
        self._full_size: tuple[int, int] | None = None
        self._zoom = 1.0
        self._fit = True
        # 影像實際繪製在控件內的矩形：座標換算的唯一依據
        self._drawn = QRect()

    def set_image(self, array: np.ndarray) -> None:
        img = QImage(array.data, array.shape[1], array.shape[0],
                     array.strides[0], QImage.Format_Grayscale8)
        # 保持記憶體有效，QImage 不會自行複製
        img = img.copy()
        self._pixmap = QPixmap.fromImage(img)
        self.setText("")
        self.update_view()

    def set_rgb(self, array: np.ndarray) -> None:
        """顯示原始彩色影像（已轉為 RGB888）。"""
        rgb = np.ascontiguousarray(array, dtype=np.uint8)
        img = QImage(rgb.data, rgb.shape[1], rgb.shape[0],
                     rgb.strides[0], QImage.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(img)
        self.setText("")
        self.update_view()

    def clear_image(self) -> None:
        self._pixmap = None
        self._scaled = None
        self._drawn = QRect()
        self.setText("尚未載入影像\n\n請點選「開啟 JPG」開始")
        self.update()

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
        self._scaled = None
        self._recompute()
        self.update()

    def _recompute(self) -> None:
        """算出影像在控件內的實際矩形，並預先縮放。"""
        if self._pixmap is None:
            self._drawn = QRect()
            self._sync_minimum(0, 0)
            return

        m = self.contentsMargins()
        avail_w = max(1, self.width() - m.left() - m.right())
        avail_h = max(1, self.height() - m.top() - m.bottom())
        sw, sh = self._pixmap.width(), self._pixmap.height()
        if sw <= 0 or sh <= 0:
            self._drawn = QRect()
            self._sync_minimum(0, 0)
            return

        if self._fit:
            s = min(avail_w / sw, avail_h / sh)
            dw = max(1, min(avail_w, int(round(sw * s))))
            dh = max(1, min(avail_h, int(round(sh * s))))
        else:
            # 放大時不可夾在可視區內，否則放大按鈕會完全沒有作用。
            # 讓控件本身長到影像那麼大，外層 QScrollArea 就會出現捲軸。
            s = self._zoom
            dw = max(1, int(round(sw * s)))
            dh = max(1, int(round(sh * s)))

        self._drawn = QRect(m.left() + (avail_w - dw) // 2,
                            m.top() + (avail_h - dh) // 2, dw, dh)

        mode = (Qt.SmoothTransformation if s >= 1.0
                else Qt.FastTransformation)
        self._scaled = self._pixmap.scaled(dw, dh, Qt.IgnoreAspectRatio,
                                           mode)
        self._sync_minimum(dw, dh)

    def _sync_minimum(self, dw: int, dh: int) -> None:
        """讓 QScrollArea 知道實際需要多大捲動範圍。"""
        m = self.contentsMargins()
        if dw <= 0 or dh <= 0:
            want = QSize(MIN_VIEW_W, MIN_VIEW_H)
        elif self._fit:
            want = QSize(MIN_VIEW_W, MIN_VIEW_H)
        else:
            want = QSize(dw + m.left() + m.right(),
                         dh + m.top() + m.bottom())
        if self.minimumSize() != want:
            self.setMinimumSize(want)
            self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self.update_view()

    # ── 裁切指示框 ────────────────────────────────────────
    def set_crop(self, x: int, y: int, w: int, h: int) -> None:
        """設定裁切範圍（全解析度座標），並在圖上畫出指示框。"""
        self._crop = (x, y, w, h)
        self.update()

    def crop_to_image(self, px: int, py: int) -> tuple[int, int] | None:
        """把視窗座標換算回「整張原圖」座標。

        總覽顯示的是縮圖，但裁切框與細節視窗都使用全解析度座標。
        兩者比例不同，若直接把縮圖座標當全解析度座標使用，
        24MP 影像會有 23% 以上的定位誤差。
        """
        if self._pixmap is None or self._drawn.isEmpty():
            return None
        # 點在影像外的空白處不處理
        if not self._drawn.contains(px, py):
            return None

        fw, fh = self._full_size or (self._pixmap.width(),
                                     self._pixmap.height())
        ix = int((px - self._drawn.left()) / self._drawn.width() * fw)
        iy = int((py - self._drawn.top()) / self._drawn.height() * fh)
        return (max(0, min(fw - 1, ix)), max(0, min(fh - 1, iy)))

    def set_full_size(self, width: int, height: int) -> None:
        """告知總覽所顯示的縮圖對應的原圖尺寸。"""
        self._full_size = (width, height)

    def drawn_rect(self) -> QRect:
        return QRect(self._drawn)

    def paintEvent(self, event) -> None:  # noqa: N802
        # super() 只負責畫樣式表的框線與底色；QLabel 本身沒有 pixmap
        # 與文字，所以不會畫出多餘的東西。
        super().paintEvent(event)

        if self._pixmap is None or self._scaled is None \
                or self._drawn.isEmpty():
            return

        p = QPainter(self)
        p.drawPixmap(self._drawn.topLeft(), self._scaled)

        if self._crop is not None:
            # 裁切框在全解析度座標，須換成顯示矩形內的相對位置
            x, y, w, h = self._crop
            fw, fh = self._full_size or (self._pixmap.width(),
                                         self._pixmap.height())
            dx = self._drawn.left() + x / fw * self._drawn.width()
            dy = self._drawn.top() + y / fh * self._drawn.height()
            dw = w / fw * self._drawn.width()
            dh = h / fh * self._drawn.height()
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(QColor(255, 90, 150), 2))
            p.setBrush(QBrush(QColor(255, 120, 175, 40)))
            p.drawRect(QRectF(dx, dy, dw, dh))
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = self.crop_to_image(int(event.position().x()),
                                 int(event.position().y()))
        if pos is not None:
            self.crop_clicked.emit(pos[0], pos[1])
            event.accept()
            return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1360, 880)

        self._gray: np.ndarray | None = None       # 預覽用灰階（縮圖）
        self._full_gray: np.ndarray | None = None  # 全解析度灰階
        self._rgb: np.ndarray | None = None        # 預覽用原始彩色
        self._result: np.ndarray | None = None     # 最近一次預覽輸出
        self._mode = "原圖"                         # 目前預覽模式
        self._preview_scale = 1.0                  # 預覽縮圖的比例
        self._source_path: str | None = None
        self._seed = 0

        self._build_ui()
        self._build_menu()

        self.controller = PreviewController(self)
        self.controller.ready.connect(self._on_preview)
        self.controller.failed.connect(self._on_error)
        self.controller.busy_changed.connect(self._on_busy)

        # 匯出同樣在背景執行緒進行，24MP 約需 10 秒
        self.export_ctrl = ExportController(self)
        self.export_ctrl.done.connect(self._on_export_done)
        self.export_ctrl.failed.connect(self._on_export_failed)

        self.detail_ctrl = PreviewController(self)
        self.detail_ctrl.ready.connect(self.detail.set_result)
        self.detail_ctrl.failed.connect(self._on_error)
        self.detail_ctrl.busy_changed.connect(self._on_detail_busy)

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
        # QScrollArea 預設會畫一圈外框，疊在影像檢視區的虛線外，
        # 看起來就是一條突兀的灰色實線。這裡明確移除。
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        right = QWidget()
        right.setMinimumWidth(PANEL_MIN_WIDTH)
        right.setMaximumWidth(PANEL_MAX_WIDTH)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_controls())

        # ── 控制面板捲動區 ──────────────────────────────────
        # 參數項目較多，視窗較矮時若沒有捲動區，下半段的參數會被
        # 直接切掉而看不到。改為放入捲動區並固定寬度範圍，
        # 確保任何視窗大小下都能完整瀏覽。
        panel_scroll = QScrollArea()
        panel_scroll.setWidget(right)
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        panel_scroll.setFrameShape(QScrollArea.NoFrame)
        panel_scroll.setMinimumWidth(PANEL_MIN_WIDTH)
        panel_scroll.setMaximumWidth(PANEL_MAX_WIDTH)
        panel_scroll.setFocusPolicy(Qt.NoFocus)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(scroll)
        split.addWidget(panel_scroll)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([1000, PANEL_MAX_WIDTH])

        # ── 細節放大視窗 ──────────────────────────────────
        # 以全解析度計算指定區域，結果與匯出檔案逐像素相同，
        # 可真正檢視墨點細節。做成浮動視窗疊在主預覽右下角，
        # 不佔固定版面；可拖曳移動、往左上拉大、或直接關閉。
        self.detail = DetailPane()
        self.detail.crop_changed.connect(self._on_crop_changed)
        self.view.crop_clicked.connect(self.detail.move_crop)

        self.detail_win = DetailWindow(self.detail, parent=self)
        self.detail_win.close_requested.connect(self._on_detail_close)
        self.view.installEventFilter(self)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(split)

        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(top)

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

        # 墨點
        dots, dl = build_group("墨點")
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems(DOT_SHAPES)
        self.cmb_shape.currentIndexChanged.connect(self._on_changed)
        add_row(dl, "墨點形狀", self.cmb_shape)

        self.sld_freq = SliderSpin(5.0, 200.0, 40.0, 1, 1.0, " lpi")
        self.sld_angle = SliderSpin(0.0, 90.0, 45.0, 1, 1.0, " °")
        for w, name in ((self.sld_freq, "網屏線數"),
                        (self.sld_angle, "網屏角度")):
            w.changed.connect(self._on_changed)
            add_row(dl, name, w)
        layout.addWidget(dots)

        # 印刷尺寸：決定 dpi，dpi 再與網屏線數一起決定墨點大小。
        # 舊版把「解析度」直接放上面板，但它與網屏線數、顆粒粗細三者
        # 只透過比值影響同一件事，而且面板顯示值與實際送進演算的值並不
        # 相同。現在只填「印多寬」，解析度由畫面推導並只讀顯示。
        size_box, sl = build_group("印刷尺寸")

        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(["mm", "寸"])
        self.cmb_unit.currentIndexChanged.connect(self._on_unit_changed)

        self.sld_width = SliderSpin(20.0, 1000.0, 152.4, 1, 1.0, " mm")
        self.sld_width.changed.connect(self._on_width_changed)
        self._width_mm_now = 152.4      # 真實毫米值快取
        add_row(sl, "印刷寬度", self.sld_width)
        add_row(sl, "單位", self.cmb_unit)

        self.lbl_dpi = QLabel("—")
        self.lbl_dpi.setObjectName("readoutValue")
        add_row(sl, "實際解析度", self.lbl_dpi)

        self.lbl_metrics = QLabel("—")
        self.lbl_metrics.setObjectName("readoutValue")
        self.lbl_metrics.setWordWrap(True)
        add_row(sl, "墨點數值", self.lbl_metrics)
        layout.addWidget(size_box)

        # 墨點外觀
        look, kl = build_group("墨點外觀")
        # 占比以百分比顯示，與下方說明文字一致；內部再換算成 0~1
        self.sld_stoch = SliderSpin(0.0, 100.0, 0.0, 0, 1.0, " %")
        self.sld_irreg = SliderSpin(0.0, 1.0, 0.0, 2, 0.01, "")
        self.sld_gain = SliderSpin(0.0, 0.6, 0.15, 2, 0.01, "")
        for w, name in ((self.sld_stoch, "隨機墨點占比"),
                        (self.sld_irreg, "墨點不規則"),
                        (self.sld_gain, "墨點擴大")):
            w.changed.connect(self._on_changed)
            add_row(kl, name, w)

        # 墨點大小範圍：取代舊版「最小墨點 / 最大墨點」。
        # 舊版那兩個參數夾在亮度上，名稱與作用相反，預設值還會強迫
        # 純白區印出 4.9% 墨量，高光因此出現一堆幾像素的碎點。
        self.rng_ink = InkRange(0.0, 1.0)
        self.rng_ink.changed.connect(self._on_changed)
        add_row(kl, "墨點大小範圍", self.rng_ink)

        tip = QLabel("墨點大小範圍：0 % = 紙白無點，100 % = 完全密實填充")
        tip.setWordWrap(True)
        tip.setObjectName("hintText")
        kl.addWidget(tip)

        tip2 = QLabel("隨機墨點占比 0% = 隨機顆粒，100% = 傳統有序墨點")
        tip2.setWordWrap(True)
        tip2.setObjectName("hintText")
        kl.addWidget(tip2)
        layout.addWidget(look)

        # 印刷與隨機
        misc, ml = build_group("印刷與隨機")
        self.sld_noise = SliderSpin(8, 128, 64, 0, 4.0, " px")
        self.sld_noise.changed.connect(self._on_changed)
        add_row(ml, "藍雜訊尺寸", self.sld_noise)

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

        view_menu.addSeparator()

        self.act_detail = QAction("細節放大視窗", self)
        self.act_detail.setCheckable(True)
        self.act_detail.setChecked(True)
        self.act_detail.setShortcut("Ctrl+D")
        self.act_detail.toggled.connect(self.toggle_detail)
        view_menu.addAction(self.act_detail)

        help_menu = bar.addMenu("說明")
        act_about = QAction("關於", self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)

    def _update_actions(self) -> None:
        has = self._gray is not None
        self.act_export.setEnabled(has)
        self.btn_export.setEnabled(has)

    # ── 參數 ──────────────────────────────────────────────
    MM_PER_INCH = 25.4

    def _width_mm(self) -> float:
        """目前輸入的印刷寬度，統一換算成 mm。"""
        v = self.sld_width.value()
        return v * self.MM_PER_INCH if self._unit_is_inch() else v

    def _sync_width_cache(self) -> None:
        """把「真實毫米值」寫進快取，供單位切換時使用。"""
        self._width_mm_now = self._width_mm()

    def _unit_is_inch(self) -> bool:
        return self.cmb_unit.currentIndex() == 1

    def _on_unit_changed(self, *_args) -> None:
        """切換單位時換算顯示值，不改變實際寬度。

        注意 currentIndexChanged 是在索引「已經換掉」之後才送出，
        此時 _width_mm() 會用新單位去讀舊數值，算出來的結果是錯的
        （152.4 mm 切到寸會變成 152.4 x 25.4）。因此改用 _width_mm_now
        這個「目前單位下的真實毫米值」快取。
        """
        mm = self._width_mm_now
        self._apply_unit_range()
        shown = mm / self.MM_PER_INCH if self._unit_is_inch() else mm
        self.sld_width.spin.blockSignals(True)
        self.sld_width.spin.setValue(shown)
        self.sld_width.spin.blockSignals(False)
        self.sld_width.slider.blockSignals(True)
        self.sld_width.slider.setValue(self.sld_width._to_slider(shown))
        self.sld_width.slider.blockSignals(False)
        self._refresh_readout()
        self._on_changed()

    def _apply_unit_range(self) -> None:
        """調整輸入框的範圍與單位字樣。

        setRange 會夾住當前值並送出 valueChanged，若不擋住訊號，
        這個「夾制」會被當成使用者調整，寫壞毫米值快取。
        """
        self.sld_width.spin.blockSignals(True)
        try:
            if self._unit_is_inch():
                self.sld_width.spin.setRange(0.8, 40.0)
                self.sld_width.spin.setSingleStep(0.1)
                self.sld_width.spin.setSuffix(" 寸")
            else:
                self.sld_width.spin.setRange(20.0, 1000.0)
                self.sld_width.spin.setSingleStep(1.0)
                self.sld_width.spin.setSuffix(" mm")
        finally:
            self.sld_width.spin.blockSignals(False)

    def _on_width_changed(self, *_args) -> None:
        self._sync_width_cache()
        self._refresh_readout()
        self._on_changed()

    def _resolution_for(self, px_width: int) -> float:
        """由「印多寬」與實際送去算的像素寬度推導 dpi。

        px_width 必須是**真的會送去算的那個寬度**：
          匯出與細節窗格 -> 原圖寬度
          縮圖預覽       -> 縮圖寬度
        舊版在 _params 裡靠 for_preview 旗標暗中縮放解析度，現在改成
        由呼叫端明說要算多寬的影像，行為與面板顯示一致。
        """
        if px_width <= 0 or self._width_mm() <= 0:
            return 300.0
        return px_width / self._width_mm() * self.MM_PER_INCH

    def _params(self, px_width: int | None = None) -> HalftoneParams:
        """組出參數。

        px_width 為實際送去計算的像素寬度；未指定時用原圖寬度
        （即匯出／細節窗格的設定）。
        """
        if px_width is None:
            px_width = (self._full_gray.shape[1]
                        if self._full_gray is not None else 0)
        lo, hi = self.rng_ink.values()
        return HalftoneParams(
            print_width_mm=self._width_mm(),
            resolution=self._resolution_for(px_width),
            frequency=self.sld_freq.value(),
            stochastic=self.sld_stoch.value() / 100.0,
            angle=self.sld_angle.value(),
            dot_shape=self.cmb_shape.currentIndex(),
            shape_amount=self.sld_irreg.value(),
            noise_size=int(self.sld_noise.value()),
            dot_gain=self.sld_gain.value(),
            min_ink=lo,
            max_ink=hi,
            seed=self._seed,
        )

    def _refresh_readout(self) -> None:
        """更新印刷尺寸區的只讀數值。"""
        px_w = (self._full_gray.shape[1]
                if self._full_gray is not None else 0)
        if px_w <= 0:
            self.lbl_dpi.setText("載入影像後顯示")
            self.lbl_metrics.setText("載入影像後顯示")
            return

        params = self._params(px_w)
        m = physical_metrics(params)

        self.lbl_dpi.setText(f"{m['dpi']:.0f} dpi")

        lines = [
            f"間距　　{m['pitch_mm']:.3f} mm（{m['pitch_px']:.0f} px）",
            f"中值墨點 {m['mid_mm']:.3f} mm（{m['mid_px']:.1f} px）",
            f"最小墨點 {m['min_mm']:.3f} mm（{m['min_px']:.1f} px）",
        ]
        if params.min_ink > 0.0 and m["min_px"] < 1.5:
            lines.append("⚠ 最小墨點不足 1.5 px，印不出來")
        if m["pitch_px"] < 1.0:
            lines.append("⚠ 網屏線數過高，已超出影像解析度")
        self.lbl_metrics.setText("\n".join(lines))

    # ── 事件 ──────────────────────────────────────────────
    def _on_changed(self, *_args) -> None:
        """參數變動：以節流方式更新預覽。"""
        self._debounce.start()

    def _apply_preview(self) -> None:
        # dpi 依賴影像像素寬度，載入影像後必須重算只讀數值
        self._refresh_readout()
        if self._gray is None:
            return
        # 預覽用縮圖：dpi 要依縮圖實際寬度推導，否則墨點相對整張圖
        # 會被放大數倍，預覽與實際產出對不上。這裡明說送進去的是縮圖。
        self.controller.request(self._params(self._gray.shape[1]))
        self._apply_detail()

    def _apply_detail(self) -> None:
        """以全解析度計算裁切區域，結果與匯出檔案逐像素相同。"""
        if self._full_gray is None:
            return
        crop = self.detail.crop_source()
        if crop is None or crop.size == 0:
            return
        cx, cy = self.detail.crop_rect()[:2]
        fh, fw = self._full_gray.shape
        # 裁切區塊是原圖的一部分，像素尺度與原圖相同，所以用原圖寬度
        self.detail_ctrl.request(self._params(fw), crop, (cx, cy), (fw, fh))

    def _on_preview(self, result: np.ndarray) -> None:
        self._result = result
        self._mode = "墨點預覽"
        self.view.set_image(result)
        self._update_compare()

    def on_toggle_compare(self) -> None:
        """在原始彩色影像與墨點預覽之間切換，用於對照。"""
        if self._rgb is None:
            return
        if self._mode == "原圖":
            if self._result is not None:
                self.view.set_image(self._result)
                self._mode = "墨點預覽"
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
        self.btn_compare.setText("顯示原圖" if show_original else "顯示墨點")

    def _on_error(self, message: str) -> None:
        self.progress.setVisible(False)
        QMessageBox.warning(self, "處理失敗", message)

    def _on_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)

    def _on_detail_busy(self, busy: bool) -> None:
        self.detail.lbl_info.setEnabled(not busy)

    def _on_crop_changed(self, x: int, y: int, w: int, h: int) -> None:
        """裁切範圍改變時更新總覽圖上的指示框並重算細節。"""
        self.view.set_crop(x, y, w, h)
        self._apply_detail()

    def on_random_seed(self) -> None:
        self._seed = int(np.random.default_rng().integers(0, 1_000_000))
        self._debounce.start()

    def on_reset_params(self) -> None:
        d = HalftoneParams()
        self.sld_freq.set_value(d.frequency)
        self.sld_angle.set_value(d.angle)
        self.cmb_shape.setCurrentIndex(d.dot_shape)
        self.sld_stoch.set_value(d.stochastic * 100.0)
        self.sld_irreg.set_value(d.shape_amount)
        self.sld_gain.set_value(d.dot_gain)
        self.rng_ink.set_values(d.min_ink, d.max_ink)
        self.sld_noise.set_value(d.noise_size)
        # 印刷寬度預設六寸，切到寸時顯示值也要跟著換
        if self._unit_is_inch():
            shown = d.print_width_mm / self.MM_PER_INCH
        else:
            shown = d.print_width_mm
        self.sld_width.spin.blockSignals(True)
        self.sld_width.spin.setValue(shown)
        self.sld_width.spin.blockSignals(False)
        self.sld_width.slider.blockSignals(True)
        self.sld_width.slider.setValue(self.sld_width._to_slider(shown))
        self.sld_width.slider.blockSignals(False)
        self._width_mm_now = d.print_width_mm
        self._seed = d.seed
        self._refresh_readout()
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

        # 預覽縮圖的比例：預覽時解析度需依此比例同步縮小，
        # 否則墨點相對整張圖會被放大，預覽與實際產出便對不上。
        self._preview_scale = (self._gray.shape[1] / full.shape[1]
                               if full.shape[1] else 1.0)

        # 總覽顯示縮圖，但裁切框用全解析度座標，需告知對應的原圖尺寸
        self.view.set_full_size(full.shape[1], full.shape[0])

        self.view.set_rgb(self._rgb)
        self.view.fit()
        self.detail.set_gray(full)
        self.controller.set_gray(self._gray)
        self._update_actions()

        # 影像載入後才顯示浮動視窗，否則開程式時會出現空白小窗
        if self.act_detail.isChecked() and not self.detail_win.isVisible():
            self.detail_win.anchor_to(self.view)
            self.detail_win.show()
            self.detail_win.raise_()
            self.detail_win.reanchor()

        self.setWindowTitle(f"{APP_TITLE} — {name}")
        self.lbl_size.setText(
            f"原始尺寸 {full.shape[1]} × {full.shape[0]} px"
            + (f"\n預覽 {self._gray.shape[1]} × {self._gray.shape[0]} px"
               f"（{self._preview_scale:.0%}）" if small else ""))
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

        # JPEG 為有損壓縮，二值墨點邊緣會出現灰階雜訊，先行確認
        if is_lossy_format(fmt):
            ok = QMessageBox.question(
                self, "確認以 JPEG 輸出",
                "JPEG 是有損壓縮格式，純黑白的墨點邊緣在存檔後\n"
                "會出現灰階雜訊，可能影響製版品質。\n\n"
                "程式會以最高畫質輸出以降低失真，但仍有殘留。\n"
                "若要拿來實際製版，建議改用 PNG（無損）。\n\n"
                "仍要以 JPEG 輸出嗎？")
            if ok != QMessageBox.Yes:
                return

        self.progress.setVisible(True)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._export_path = path
        self._export_fmt = fmt
        self.export_ctrl.start(self._full_gray, params, path)

    def _on_detail_close(self) -> None:
        """關閉鈕：隱藏視窗並同步取消選單勾選。

        必須一併取消勾選，否則選單仍顯示為啟用，使用者得點兩次
        才能重新叫出視窗。
        """
        self.detail_win.hide()
        if hasattr(self, "act_detail"):
            self.act_detail.blockSignals(True)
            self.act_detail.setChecked(False)
            self.act_detail.blockSignals(False)
        self._set_status("已關閉細節放大視窗（檢視選單可重新開啟）")

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        dw = getattr(self, "detail_win", None)
        if dw is None:
            return super().eventFilter(obj, event)

        # 主預覽區被拉伸（例如拖曳分隔線）時，右下角跟著動。
        # 主視窗本身不會觸發 resizeEvent，所以要另外掛在預覽上。
        if obj is self.view and event.type() == QEvent.Resize:
            dw.reanchor()
            return False
        return super().eventFilter(obj, event)

    def event(self, e) -> bool:  # noqa: N802
        # 主視窗被點選而提到最前面時，Windows 可能把浮動視窗壓到後面，
        # 這裡在啟用時補一次置前。
        if e.type() == QEvent.WindowActivate:
            dw = getattr(self, "detail_win", None)
            if dw is not None and dw.isVisible():
                dw.raise_()
        return super().event(e)

    def toggle_detail(self, checked: bool) -> None:  # noqa: N802
        if checked:
            self.detail_win.anchor_to(self.view)
            self.detail_win.show()
            self.detail_win.raise_()
            # show() 之後視窗實際尺寸才確定，再錨定一次
            self.detail_win.reanchor()
        else:
            self.detail_win.hide()

    def _on_export_done(self, path: str, fmt: str, ink: float,
                        width: int, height: int) -> None:
        QApplication.restoreOverrideCursor()
        self.progress.setVisible(False)

        self._set_status(
            f"已匯出 {path.rsplit(chr(92), 1)[-1]}"
            f"（{width}×{height}，上墨率 {ink:.1f}%）")
        bits = "1-bit 雙色" if fmt == "PNG" else "8 位元灰階"
        note = ("\n\n注意：JPEG 為有損格式，墨點邊緣可能有灰階雜訊。"
                if is_lossy_format(fmt) else "")
        QMessageBox.information(
            self, "匯出完成",
            f"已另存至：\n{path}\n\n"
            f"格式 {fmt}（{bits}，不含任何中繼資料）\n"
            f"尺寸 {width} × {height} px\n"
            f"上墨率 {ink:.1f}%{note}")

    def _on_export_failed(self, message: str) -> None:
        QApplication.restoreOverrideCursor()
        self.progress.setVisible(False)
        QMessageBox.critical(self, "匯出失敗", message)
        self._set_status("匯出失敗")

    def on_about(self) -> None:
        QMessageBox.about(
            self, "關於",
            f"<b>{APP_TITLE}</b><br><br>"
            "絲網印刷用隨機顆粒半調墨點工具。<br>"
            "隨機墨點占比可連續調整：0% 為藍雜訊隨機顆粒，"
            "100% 為傳統有序墨點。<br><br>"
            "純 NumPy 實作，不依賴 GIMP 或其他外部影像軟體。")

    def _set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        # 浮動視窗是獨立頂層視窗，不會跟著主視窗走，必須手動跟隨，
        # 否則主視窗一移動，右下角就不再對齊。
        dw = getattr(self, "detail_win", None)
        if dw is not None:
            dw.reanchor()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        dw = getattr(self, "detail_win", None)
        if dw is not None:
            dw.reanchor()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.controller.shutdown()
        self.detail_ctrl.shutdown()
        self.export_ctrl.shutdown()
        self.detail_win.close()
        super().closeEvent(event)


def main() -> int:
    # 注意：不可設定 Qt.AA_DontCreateNativeWidgetSiblings。
    # 該屬性是為 QOpenGLWidget + QOpenGLWindow 的情境設計，
    # 對一般 Widgets 介面會破壞原生元件的共用與繪製，
    # 在打包後會導致右側控制面板整片消失。
    app = QApplication(sys.argv)
    app.setApplicationName("Halftone Studio")
    app.setStyle("Fusion")
    app.setStyleSheet(get_stylesheet())

    window = MainWindow()
    window.show()
    return app.exec()





