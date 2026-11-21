#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""和平精英地铁逃生录屏播报截图工具 - 桌面界面。"""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
from PySide6.QtCore import (
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QStyle,
    QDialog,
    QVBoxLayout,
    QWidget,
)

# 支持通过环境变量指定独立的模型目录。项目本地存在 models 目录时也直接使用，
# 方便离线运行；否则由 PaddleOCR 按默认规则下载模型到其缓存目录。
_MODEL_DIR_OVERRIDE = os.environ.get("PEACE_ELITE_MODEL_DIR")
_LOCAL_MODEL_DIR = Path(__file__).resolve().parent / "models"
if _MODEL_DIR_OVERRIDE:
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", _MODEL_DIR_OVERRIDE)
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
elif _LOCAL_MODEL_DIR.is_dir():
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(_LOCAL_MODEL_DIR))
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import metro_announcement_capture as core


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v"}
ACCENT = "#C7FF4A"
ACCENT_DARK = "#101408"
BACKGROUND = "#090B0C"
SURFACE = "#121619"
SURFACE_RAISED = "#181D20"
BORDER = "#2A3135"
TEXT = "#F2F5F3"
MUTED = "#8D989D"
DANGER = "#FF716A"
RESULT_IMAGE_MAX_WIDTH = 1600


APP_STYLE = f"""
QWidget {{
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}}
QWidget#root {{
    background: {BACKGROUND};
}}
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QFrame#sideCard {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#eventGroup {{
    background: #111619;
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#captureCard {{
    background: #171D20;
    border: 1px solid #2B3438;
    border-radius: 12px;
}}
QFrame#captureCard:hover {{
    background: #1C2327;
    border-color: #465158;
}}
QLabel#eventTitle {{
    font-size: 17px;
    font-weight: 700;
}}
QLabel#eventCount {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#captureIndex {{
    color: {ACCENT};
    font-size: 11px;
    font-weight: 700;
}}
QLabel#captureImage {{
    background: #080A0B;
    border-radius: 8px;
}}
QLabel#resultEmpty {{
    color: {MUTED};
    font-size: 15px;
}}
QScrollArea {{
    border: 0;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QDialog {{
    background: {BACKGROUND};
}}
QLabel#brandMark {{
    background: {ACCENT};
    color: #0A0C08;
    border-radius: 10px;
    font-size: 18px;
    font-weight: 800;
}}
QLabel#brand {{
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#brandSub {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel#eyebrow {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#title {{
    font-size: 23px;
    font-weight: 700;
}}
QLabel#sectionTitle {{
    font-size: 14px;
    font-weight: 700;
}}
QLabel#muted {{
    color: {MUTED};
}}
QLabel#meta {{
    color: #B7C0C3;
    font-size: 12px;
}}
QLabel#fileName {{
    font-size: 14px;
    font-weight: 700;
}}
QLabel#statusPill {{
    background: #20271D;
    color: {ACCENT};
    border: 1px solid #3A4727;
    border-radius: 11px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#roiState {{
    color: {MUTED};
    font-size: 13px;
}}
QPushButton {{
    min-height: 38px;
    padding: 0 16px;
    background: #22282C;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #2A3135;
    border-color: #404A4F;
}}
QPushButton:pressed {{
    background: #1B2023;
}}
QPushButton:disabled {{
    color: #616B70;
    background: #171B1D;
    border-color: #242A2D;
}}
QPushButton#primary {{
    min-height: 48px;
    background: {ACCENT};
    color: {ACCENT_DARK};
    border: 0;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 800;
}}
QPushButton#primary:hover {{
    background: #D6FF73;
}}
QPushButton#primary:pressed {{
    background: #B5E83E;
}}
QPushButton#primary:disabled {{
    color: #68715B;
    background: #262D20;
}}
QPushButton#quiet {{
    background: transparent;
    border-color: transparent;
    color: #C6CFCB;
}}
QPushButton#quiet:hover {{
    background: #1B2124;
    border-color: #2C3438;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: #2A3135;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    background: {TEXT};
    border: 2px solid #090B0C;
    border-radius: 7px;
}}
QProgressBar {{
    height: 7px;
    background: #252C2F;
    border: 0;
    border-radius: 3px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}
QSpinBox {{
    min-height: 34px;
    padding: 0 10px;
    background: #0F1315;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 9px;
    font-weight: 700;
}}
QSpinBox:hover {{
    border-color: #4B585E;
}}
QSpinBox:focus {{
    border-color: {ACCENT};
}}
QToolTip {{
    background: #20262A;
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px;
}}
"""


def bgr_to_qimage(frame: Any) -> QImage:
    """把 OpenCV BGR 画面转换为 Qt 图像。"""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width, channels = rgb.shape
    return QImage(
        rgb.data,
        width,
        height,
        channels * width,
        QImage.Format.Format_RGB888,
    ).copy()


@dataclass(frozen=True)
class CaptureRecord:
    """一张只存在于当前软件会话中的结果图。"""

    event_index: int
    capture_index: int
    pixmap: QPixmap
    text_signature: str = ""


class ClickableImage(QLabel):
    clicked = Signal()

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()
        self.setObjectName("captureImage")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(494, 126)
        self.setPixmap(
            pixmap.scaled(
                self.size() - QSize(12, 12),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class CaptureCard(QFrame):
    def __init__(self, record: CaptureRecord) -> None:
        super().__init__()
        self.record = record
        self.setObjectName("captureCard")
        self.setFixedWidth(520)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        event_label = QLabel(f"截图 {record.capture_index:02d}")
        event_label.setObjectName("captureIndex")
        header.addWidget(event_label)
        header.addStretch(1)
        index_label = QLabel("点击查看")
        index_label.setObjectName("eventCount")
        header.addWidget(index_label)
        layout.addLayout(header)

        image = ClickableImage(record.pixmap)
        image.setToolTip("点击查看大图")
        image.clicked.connect(self.clicked_for_record)
        layout.addWidget(image)

    def clicked_for_record(self) -> None:
        viewer = CaptureViewer(self.record, self.window())
        viewer.exec()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_for_record()
        super().mousePressEvent(event)


class CaptureViewer(QDialog):
    def __init__(self, record: CaptureRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"截图 {record.capture_index:02d}")
        self.resize(1180, 620)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        title = QLabel(f"截图 {record.capture_index:02d}")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setPixmap(
            record.pixmap.scaled(
                QSize(1120, 500),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        layout.addWidget(image_label, 1)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)


class VideoSource:
    """维护当前视频和可读取的帧信息。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.capture = cv2.VideoCapture(str(path))
        if not self.capture.isOpened():
            self.capture.release()
            raise core.ScriptError(
                "无法打开这个视频。请确认文件未损坏，且格式受 OpenCV 支持。"
            )

        self.width = int(round(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        self.height = int(round(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        self.frame_count = int(round(self.capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        if self.width <= 0 or self.height <= 0:
            self.close()
            raise core.ScriptError("无法读取视频分辨率。")

    def frame_at(self, index: int) -> Any:
        if self.frame_count > 0:
            index = max(0, min(self.frame_count - 1, index))
        else:
            index = max(0, index)
        self.capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        success, frame = self.capture.read()
        if not success or frame is None:
            raise core.ScriptError("无法读取这个视频帧。")
        return frame

    def close(self) -> None:
        if getattr(self, "capture", None) is not None:
            self.capture.release()
            self.capture = None


class VideoCanvas(QWidget):
    """显示视频帧，并允许用户直接在画面上拖动框选。"""

    roiChanged = Signal(object)
    videoDropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setMinimumSize(QSize(540, 350))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._pixmap: QPixmap | None = None
        self._image_rect = QRectF()
        self._selection: QRect | None = None
        self._drag_origin: QPoint | None = None
        self._source_size = QSize()

    def set_frame(self, frame: Any, clear_selection: bool = True) -> None:
        image = bgr_to_qimage(frame)
        self._pixmap = QPixmap.fromImage(image)
        self._source_size = image.size()
        if clear_selection:
            self._selection = None
            self.roiChanged.emit(None)
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._image_rect = QRectF()
        self._selection = None
        self._source_size = QSize()
        self.roiChanged.emit(None)
        self.update()

    def selection(self) -> QRect | None:
        if self._selection is None:
            return None
        return QRect(self._selection)

    def _display_rect(self) -> QRectF:
        if self._pixmap is None:
            return QRectF()
        available = QRectF(self.rect()).adjusted(18, 18, -18, -18)
        scaled = self._pixmap.size()
        scaled.scale(available.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF(
            available.center().x() - scaled.width() / 2,
            available.center().y() - scaled.height() / 2,
            scaled.width(),
            scaled.height(),
        )

    def _to_source(self, point: QPoint) -> QPoint | None:
        if self._pixmap is None or self._image_rect.isEmpty():
            return None
        if not self._image_rect.contains(point):
            return None
        x = int(
            (point.x() - self._image_rect.left())
            * self._source_size.width()
            / self._image_rect.width()
        )
        y = int(
            (point.y() - self._image_rect.top())
            * self._source_size.height()
            / self._image_rect.height()
        )
        return QPoint(
            max(0, min(self._source_size.width() - 1, x)),
            max(0, min(self._source_size.height() - 1, y)),
        )

    def _selection_display_rect(self) -> QRectF | None:
        if self._selection is None:
            return None
        sx = self._image_rect.width() / max(1, self._source_size.width())
        sy = self._image_rect.height() / max(1, self._source_size.height())
        return QRectF(
            self._image_rect.left() + self._selection.x() * sx,
            self._image_rect.top() + self._selection.y() * sy,
            self._selection.width() * sx,
            self._selection.height() * sy,
        )

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0B0E10"))

        if self._pixmap is None:
            painter.setPen(QPen(QColor("#354045"), 1, Qt.PenStyle.DashLine))
            drop_rect = QRectF(self.rect()).adjusted(22, 22, -22, -22)
            painter.drawRoundedRect(drop_rect, 14, 14)
            painter.setPen(QColor(TEXT))
            painter.setFont(QFont("Microsoft YaHei UI", 16, QFont.Weight.DemiBold))
            painter.drawText(
                drop_rect.adjusted(20, 0, -20, -24),
                Qt.AlignmentFlag.AlignCenter,
                "把录屏拖到这里",
            )
            painter.setPen(QColor(MUTED))
            painter.setFont(QFont("Microsoft YaHei UI", 10))
            painter.drawText(
                drop_rect.adjusted(20, 34, -20, 0),
                Qt.AlignmentFlag.AlignCenter,
                "支持 MP4、MKV、AVI、MOV 等本地视频",
            )
            return

        self._image_rect = self._display_rect()
        painter.drawPixmap(
            self._image_rect.toRect(),
            self._pixmap,
            self._pixmap.rect(),
        )

        selected = self._selection_display_rect()
        if selected is not None:
            shade = QColor(0, 0, 0, 135)
            painter.fillRect(
                QRectF(self._image_rect.left(), self._image_rect.top(), self._image_rect.width(), selected.top() - self._image_rect.top()),
                shade,
            )
            painter.fillRect(
                QRectF(self._image_rect.left(), selected.bottom(), self._image_rect.width(), self._image_rect.bottom() - selected.bottom()),
                shade,
            )
            painter.fillRect(
                QRectF(self._image_rect.left(), selected.top(), selected.left() - self._image_rect.left(), selected.height()),
                shade,
            )
            painter.fillRect(
                QRectF(selected.right(), selected.top(), self._image_rect.right() - selected.right(), selected.height()),
                shade,
            )
            painter.setPen(QPen(QColor(ACCENT), 2))
            painter.drawRoundedRect(selected, 3, 3)
            painter.setBrush(QColor(ACCENT))
            painter.setPen(Qt.PenStyle.NoPen)
            handle = 5.0
            for point in (
                selected.topLeft(),
                selected.topRight(),
                selected.bottomLeft(),
                selected.bottomRight(),
            ):
                painter.drawRect(QRectF(point.x() - handle, point.y() - handle, handle * 2, handle * 2))

            label = f"{self._selection.width()} × {self._selection.height()} px"
            painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.DemiBold))
            metrics = painter.fontMetrics()
            label_width = metrics.horizontalAdvance(label) + 18
            label_rect = QRectF(
                selected.left(),
                max(self._image_rect.top() + 6, selected.top() - 30),
                label_width,
                24,
            )
            painter.setBrush(QColor(ACCENT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(label_rect, 6, 6)
            painter.setPen(QColor(ACCENT_DARK))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(9, 11, 12, 190))
            hint = QRectF(
                self._image_rect.center().x() - 170,
                self._image_rect.top() + 18,
                340,
                36,
            )
            painter.drawRoundedRect(hint, 10, 10)
            painter.setPen(QColor(TEXT))
            painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.DemiBold))
            painter.drawText(
                hint,
                Qt.AlignmentFlag.AlignCenter,
                "按住鼠标左键，在画面上框选播报区域",
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        source = self._to_source(event.position().toPoint())
        if source is None:
            return
        self._drag_origin = source
        self._selection = QRect(source, QSize(1, 1))
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is None:
            return
        source = self._to_source(event.position().toPoint())
        if source is None:
            return
        self._selection = QRect(self._drag_origin, source).normalized()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._drag_origin is None:
            return
        source = self._to_source(event.position().toPoint())
        if source is None:
            self._selection = None
        else:
            self._selection = QRect(self._drag_origin, source).normalized()
            if self._selection.width() < core.MIN_ROI_WIDTH or self._selection.height() < core.MIN_ROI_HEIGHT:
                self._selection = None
        self._drag_origin = None
        self.roiChanged.emit(self.selection())
        self.update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in VIDEO_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in VIDEO_EXTENSIONS:
                    self.videoDropped.emit(str(path))
                    event.acceptProposedAction()
                    return
        event.ignore()


class CaptureWorker(QThread):
    """在后台加载 OCR 并处理视频，避免界面卡死。"""

    stageChanged = Signal(str)
    progressChanged = Signal(int, int, int, int)
    captureReady = Signal(int, int, object, str)
    completed = Signal(int, int, int)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, video_path: Path, roi: QRect) -> None:
        super().__init__()
        self.video_path = video_path
        self.roi = (
            roi.x(),
            roi.y(),
            roi.x() + roi.width(),
            roi.y() + roi.height(),
        )

    def run(self) -> None:
        try:
            self.stageChanged.emit("正在加载 PaddleOCR 模型")
            ocr = core.create_ocr()
            self.stageChanged.emit("GPU 正在批量检查录屏")
            summary = core.process_video(
                self.video_path,
                None,
                ocr,
                self.roi,
                capture_callback=self.captureReady.emit,
                progress_callback=self.progressChanged.emit,
                cancel_check=self.isInterruptionRequested,
            )
            self.completed.emit(*summary)
        except core.ProcessingCancelled:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self, initial_video: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("和平精英 · 播报截图")
        self.resize(1240, 800)
        self.setMinimumSize(1040, 680)

        self.video_source: VideoSource | None = None
        self.video_path: Path | None = None
        self.worker: CaptureWorker | None = None
        self.current_roi: QRect | None = None
        self.captures: list[CaptureRecord] = []

        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(80)
        self._seek_timer.timeout.connect(self._load_slider_frame)

        self._build_ui()
        self._apply_style()

        if initial_video:
            self.load_video(Path(initial_video))

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 22, 28, 26)
        outer.setSpacing(20)

        header = QHBoxLayout()
        header.setSpacing(12)
        mark = QLabel("M")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(42, 42)
        header.addWidget(mark)

        brand_column = QVBoxLayout()
        brand_column.setSpacing(1)
        brand = QLabel("METRO CAPTURE")
        brand.setObjectName("brand")
        brand_sub = QLabel("地铁逃生 · 离线录屏播报抽取")
        brand_sub.setObjectName("brandSub")
        brand_column.addWidget(brand)
        brand_column.addWidget(brand_sub)
        header.addLayout(brand_column)
        header.addStretch(1)

        private_pill = QLabel("●  内容去重 · 本地处理")
        private_pill.setObjectName("statusPill")
        header.addWidget(private_pill)
        outer.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(20)

        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(20, 18, 20, 18)
        preview_layout.setSpacing(14)

        preview_head = QHBoxLayout()
        preview_title = QLabel("录制预览")
        preview_title.setObjectName("title")
        preview_head.addWidget(preview_title)
        preview_head.addStretch(1)
        self.frame_counter = QLabel("等待选择录屏")
        self.frame_counter.setObjectName("meta")
        preview_head.addWidget(self.frame_counter)
        preview_layout.addLayout(preview_head)

        self.canvas = VideoCanvas()
        self.canvas.roiChanged.connect(self._on_roi_changed)
        self.canvas.videoDropped.connect(self._load_video_from_string)
        preview_layout.addWidget(self.canvas, 1)

        timeline = QHBoxLayout()
        timeline.setSpacing(12)
        self.prev_button = QPushButton("上一帧")
        self.prev_button.setObjectName("quiet")
        self.prev_button.setEnabled(False)
        self.prev_button.clicked.connect(lambda: self._step_frame(-1))
        timeline.addWidget(self.prev_button)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self._on_slider_value)
        timeline.addWidget(self.frame_slider, 1)
        self.next_button = QPushButton("下一帧")
        self.next_button.setObjectName("quiet")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(lambda: self._step_frame(1))
        timeline.addWidget(self.next_button)
        preview_layout.addLayout(timeline)
        content.addWidget(preview_card, 1)

        side_container = QWidget()
        side_container.setFixedWidth(344)
        side = QVBoxLayout(side_container)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(14)
        content.addWidget(side_container)

        source_card = QFrame()
        source_card.setObjectName("sideCard")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(18, 16, 18, 16)
        source_layout.setSpacing(10)
        eyebrow = QLabel("当前录屏")
        eyebrow.setObjectName("eyebrow")
        source_layout.addWidget(eyebrow)
        self.file_name = QLabel("尚未选择视频")
        self.file_name.setObjectName("fileName")
        self.file_name.setWordWrap(True)
        source_layout.addWidget(self.file_name)
        self.file_meta = QLabel("拖入视频，或从电脑中选择")
        self.file_meta.setObjectName("meta")
        source_layout.addWidget(self.file_meta)
        self.choose_button = QPushButton("选择录屏")
        self.choose_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.choose_button.clicked.connect(self._choose_video)
        source_layout.addWidget(self.choose_button)
        side.addWidget(source_card)

        roi_card = QFrame()
        roi_card.setObjectName("sideCard")
        roi_layout = QVBoxLayout(roi_card)
        roi_layout.setContentsMargins(18, 16, 18, 16)
        roi_layout.setSpacing(8)
        roi_eyebrow = QLabel("检测区域")
        roi_eyebrow.setObjectName("eyebrow")
        roi_layout.addWidget(roi_eyebrow)
        self.roi_state = QLabel("在左侧画面上拖动框选")
        self.roi_state.setObjectName("roiState")
        roi_layout.addWidget(self.roi_state)
        rule = QLabel("只在所选矩形内查找文字")
        rule.setObjectName("muted")
        roi_layout.addWidget(rule)
        side.addWidget(roi_card)

        summary_card = QFrame()
        summary_card.setObjectName("sideCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.setSpacing(9)
        summary_eyebrow = QLabel("本次任务")
        summary_eyebrow.setObjectName("eyebrow")
        summary_layout.addWidget(summary_eyebrow)
        self.interval_label = QLabel(f"OCR 采样  ·  {core.OCR_INTERVAL_SECONDS:g} 秒")
        self.interval_label.setObjectName("meta")
        summary_layout.addWidget(self.interval_label)
        gpu_rule = QLabel(
            f"GPU 批处理  ·  每批 {core.OCR_BATCH_SIZE} 帧"
        )
        gpu_rule.setObjectName("meta")
        summary_layout.addWidget(gpu_rule)
        output_rule = QLabel("结果展示  ·  截图不写入磁盘")
        output_rule.setObjectName("meta")
        summary_layout.addWidget(output_rule)
        privacy = QLabel("仅本次运行可见  ·  关闭后自动释放")
        privacy.setObjectName("meta")
        summary_layout.addWidget(privacy)

        side.addWidget(summary_card)

        dedupe_card = QFrame()
        dedupe_card.setObjectName("sideCard")
        dedupe_layout = QVBoxLayout(dedupe_card)
        dedupe_layout.setContentsMargins(18, 16, 18, 16)
        dedupe_layout.setSpacing(9)

        dedupe_title = QLabel("去重设置")
        dedupe_title.setObjectName("eyebrow")
        dedupe_layout.addWidget(dedupe_title)

        same_text_rule = QLabel("相同文字  ·  只保留最后一次")
        same_text_rule.setObjectName("sectionTitle")
        dedupe_layout.addWidget(same_text_rule)

        blank_rule = QLabel("没有文字  ·  自动移除")
        blank_rule.setObjectName("meta")
        dedupe_layout.addWidget(blank_rule)

        dedupe_disabled = QLabel("文本相似度去重  ·  已关闭")
        dedupe_disabled.setObjectName("muted")
        dedupe_layout.addWidget(dedupe_disabled)
        side.addWidget(dedupe_card)

        side.addStretch(1)

        self.start_button = QPushButton("开始分析")
        self.start_button.setObjectName("primary")
        self.start_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start_processing)
        side.addWidget(self.start_button)

        self.cancel_button = QPushButton("停止处理")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel_processing)
        side.addWidget(self.cancel_button)

        self.view_results_button = QPushButton("查看本次结果")
        self.view_results_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.view_results_button.setEnabled(False)
        self.view_results_button.clicked.connect(self._show_results_page)
        side.addWidget(self.view_results_button)

        self.status_label = QLabel("准备就绪")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        side.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        side.addWidget(self.progress)

        setup_page = QWidget()
        setup_page.setLayout(content)
        self.pages = QStackedWidget()
        self.pages.addWidget(setup_page)
        self.results_page = self._build_results_page()
        self.pages.addWidget(self.results_page)
        outer.addWidget(self.pages, 1)

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(14)
        back_button = QPushButton("返回处理")
        back_button.setObjectName("quiet")
        back_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        )
        back_button.clicked.connect(lambda: self.pages.setCurrentWidget(self.pages.widget(0)))
        header.addWidget(back_button, 0, Qt.AlignmentFlag.AlignTop)

        title_column = QVBoxLayout()
        title_column.setSpacing(3)
        title = QLabel("处理结果")
        title.setObjectName("title")
        title_column.addWidget(title)
        self.results_summary = QLabel("还没有检测结果")
        self.results_summary.setObjectName("muted")
        title_column.addWidget(self.results_summary)
        header.addLayout(title_column)
        header.addStretch(1)

        upload_again_button = QPushButton("重新上传录屏")
        upload_again_button.setObjectName("quiet")
        upload_again_button.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_DialogOpenButton
            )
        )
        upload_again_button.setToolTip("清空本轮结果并返回初始上传界面")
        upload_again_button.clicked.connect(self._restart_upload)
        header.addWidget(
            upload_again_button,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        memory_badge = QLabel("●  内存结果 · 未写入文件")
        memory_badge.setObjectName("statusPill")
        header.addWidget(memory_badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.results_list_layout = QVBoxLayout(content)
        self.results_list_layout.setContentsMargins(0, 0, 10, 12)
        self.results_list_layout.setSpacing(16)
        self.results_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif child_layout is not None:
                MainWindow._clear_layout(child_layout)  # type: ignore[arg-type]

    def _rebuild_results(self) -> None:
        self._clear_layout(self.results_list_layout)

        capture_count = len(self.captures)
        if not self.captures:
            self.results_summary.setText("还没有检测结果")
            self.view_results_button.setEnabled(False)
            empty = QLabel("本次运行没有检测到可展示的播报截图。")
            empty.setObjectName("resultEmpty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_list_layout.addWidget(empty, 1)
            return

        self.results_summary.setText(
            f"{capture_count} 张截图  ·  按捕获顺序排列  ·  "
            "点击任意图片查看大图"
        )
        self.view_results_button.setEnabled(
            self.worker is None or not self.worker.isRunning()
        )

        gallery = QFrame()
        gallery.setObjectName("eventGroup")
        gallery_layout = QVBoxLayout(gallery)
        gallery_layout.setContentsMargins(16, 16, 16, 16)
        gallery_layout.setSpacing(14)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        for index, record in enumerate(self.captures):
            card = CaptureCard(record)
            grid.addWidget(card, index // 2, index % 2)
        grid.setColumnStretch(2, 1)
        gallery_layout.addLayout(grid)
        self.results_list_layout.addWidget(gallery)

        self.results_list_layout.addStretch(1)

    def _show_results_page(self) -> None:
        if self.captures:
            self.pages.setCurrentWidget(self.results_page)

    def _restart_upload(self) -> None:
        """清空当前任务并回到初始上传界面。"""
        if self.worker is not None and self.worker.isRunning():
            return

        if self.video_source is not None:
            self.video_source.close()
            self.video_source = None

        self.video_path = None
        self.current_roi = None
        self.captures.clear()
        self._rebuild_results()

        self.canvas.clear()
        self.file_name.setText("尚未选择视频")
        self.file_meta.setText("拖入视频，或从电脑中选择")
        self.roi_state.setText("在左侧画面上拖动框选")
        self.roi_state.setStyleSheet("")
        self.status_label.setText("准备就绪")
        self.progress.setValue(0)
        self.frame_counter.setText("等待选择录屏")

        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        self.frame_slider.setEnabled(False)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.view_results_button.setEnabled(False)
        self.pages.setCurrentIndex(0)

    def _apply_style(self) -> None:
        self.setStyleSheet(APP_STYLE)

    def _load_video_from_string(self, path: str) -> None:
        self.load_video(Path(path))

    def _choose_video(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "选择录屏视频",
            "",
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.m4v);;所有文件 (*)",
        )
        if path:
            self.load_video(Path(path))

    def load_video(self, path: Path) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if not path.is_file():
            QMessageBox.warning(self, "无法打开", "视频文件不存在。")
            return
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            QMessageBox.warning(self, "无法打开", "请选择受支持的视频文件。")
            return

        if self.video_source is not None:
            self.video_source.close()
        try:
            self.video_source = VideoSource(path)
        except core.ScriptError as error:
            QMessageBox.warning(self, "无法打开视频", str(error))
            return

        self.video_path = path
        self.captures.clear()
        self._rebuild_results()
        self.pages.setCurrentIndex(0)
        self.current_roi = None
        self.start_button.setEnabled(False)

        source = self.video_source
        self.file_name.setText(path.name)
        duration = (
            source.frame_count / source.fps
            if source.fps > 0 and source.frame_count > 0
            else 0
        )
        self.file_meta.setText(
            f"{source.width} × {source.height}   ·   {duration:.1f} 秒"
        )
        self.roi_state.setText("在左侧画面上拖动框选")
        self.roi_state.setStyleSheet("")
        self.status_label.setText("选择一帧能看到播报的画面，然后拖动框选区域。")

        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)
        self.frame_slider.setEnabled(True)
        self.frame_slider.setRange(0, max(0, source.frame_count - 1))

        initial = (
            min(source.frame_count - 1, int(source.frame_count * 0.10))
            if source.frame_count > 0
            else 0
        )
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(initial)
        self.frame_slider.blockSignals(False)
        self._load_frame(initial)

    def _load_frame(self, index: int) -> None:
        if self.video_source is None:
            return
        try:
            frame = self.video_source.frame_at(index)
        except core.ScriptError as error:
            self.status_label.setText(str(error))
            return
        self.canvas.set_frame(frame)
        self.frame_counter.setText(
            f"第 {index + 1:,} 帧 / 共 {max(1, self.video_source.frame_count):,} 帧"
        )
        self.current_roi = None
        self.start_button.setEnabled(False)

    def _on_slider_value(self, _value: int) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self._seek_timer.start()

    def _load_slider_frame(self) -> None:
        if self.video_source is None:
            return
        self._load_frame(self.frame_slider.value())

    def _step_frame(self, delta: int) -> None:
        if self.video_source is None:
            return
        new_index = self.frame_slider.value() + delta
        self.frame_slider.setValue(
            max(self.frame_slider.minimum(), min(self.frame_slider.maximum(), new_index))
        )

    def _on_roi_changed(self, roi: QRect | None) -> None:
        self.current_roi = QRect(roi) if roi is not None else None
        if roi is None:
            self.roi_state.setText("在左侧画面上拖动框选")
            self.roi_state.setStyleSheet("")
        else:
            self.roi_state.setText(f"已框选  {roi.width()} × {roi.height()} px")
            self.roi_state.setStyleSheet(f"color: {ACCENT}; font-weight: 700;")
        self.start_button.setEnabled(
            self.video_path is not None
            and self.current_roi is not None
            and (self.worker is None or not self.worker.isRunning())
        )

    def _set_processing_state(self, processing: bool) -> None:
        self.choose_button.setEnabled(not processing)
        self.prev_button.setEnabled(not processing and self.video_source is not None)
        self.next_button.setEnabled(not processing and self.video_source is not None)
        self.frame_slider.setEnabled(not processing and self.video_source is not None)
        self.start_button.setVisible(not processing)
        self.cancel_button.setVisible(processing)
        self.cancel_button.setEnabled(processing)
        self.view_results_button.setEnabled(not processing and bool(self.captures))
        self.progress.setVisible(processing or self.progress.value() > 0)

    def _start_processing(self) -> None:
        if self.video_path is None or self.current_roi is None:
            return
        if self.worker is not None and self.worker.isRunning():
            return

        self.captures.clear()
        self._rebuild_results()
        self._set_processing_state(True)
        self.progress.setValue(0)
        self.status_label.setText("正在启动 OCR 引擎")

        self.worker = CaptureWorker(
            self.video_path,
            self.current_roi,
        )
        self.worker.stageChanged.connect(self.status_label.setText)
        self.worker.progressChanged.connect(self._update_progress)
        self.worker.captureReady.connect(self._on_capture_ready)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.finished.connect(lambda: self._set_processing_state(False))
        self.worker.start()

    def _update_progress(
        self,
        sampled: int,
        total: int,
        saved: int,
        events: int,
    ) -> None:
        if total > 0:
            value = min(100, int(sampled * 100 / total))
            self.progress.setRange(0, 100)
            self.progress.setValue(value)
        else:
            self.progress.setRange(0, 0)
        self.status_label.setText(
            f"已检查 {sampled:,} 个采样点  ·  已保存 {saved} 张"
        )

    def _on_completed(
        self,
        event_count: int,
        saved_count: int,
        sampled_count: int,
    ) -> None:
        self.progress.setValue(100)
        self.status_label.setText(
            f"处理完成  ·  共 {saved_count} 张截图"
        )
        self._rebuild_results()
        if self.captures:
            self.pages.setCurrentWidget(self.results_page)

    def _on_capture_ready(
        self,
        event_index: int,
        capture_index: int,
        image: Any,
        text_signature: str,
    ) -> None:
        if not text_signature:
            return

        height, width = image.shape[:2]
        if width > RESULT_IMAGE_MAX_WIDTH:
            scale = RESULT_IMAGE_MAX_WIDTH / width
            image = cv2.resize(
                image,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_AREA,
            )

        # 同一文字多次出现时，移除旧图，只在末尾保留最后一次。
        self.captures = [
            capture
            for capture in self.captures
            if capture.text_signature != text_signature
        ]
        record = CaptureRecord(
            event_index=0,
            capture_index=len(self.captures) + 1,
            pixmap=QPixmap.fromImage(bgr_to_qimage(image)),
            text_signature=text_signature,
        )
        self.captures.append(record)
        self.captures = [
            CaptureRecord(
                event_index=0,
                capture_index=index,
                pixmap=capture.pixmap,
                text_signature=capture.text_signature,
            )
            for index, capture in enumerate(self.captures, start=1)
        ]

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("处理失败，请检查提示后重试。")
        QMessageBox.critical(self, "处理失败", message)

    def _on_cancelled(self) -> None:
        self.status_label.setText("处理已停止。")

    def _cancel_processing(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.cancel_button.setEnabled(False)
            self.status_label.setText("正在停止，请稍候……")
            self.worker.requestInterruption()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None and self.worker.isRunning():
            answer = QMessageBox.question(
                self,
                "正在处理",
                "视频仍在处理中。要停止处理并退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.requestInterruption()
            self.worker.wait()

        if self.video_source is not None:
            self.video_source.close()
        event.accept()


def install_exception_handler(app: QApplication) -> None:
    """在没有控制台时，用对话框报告未处理异常。"""

    def handle_exception(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            log_path = Path(__file__).resolve().parent / "app_error.log"
            log_path.write_text(detail, encoding="utf-8")
        except OSError:
            pass
        QMessageBox.critical(
            None,
            "程序异常",
            f"程序遇到未处理的错误：\n{exc_value}\n\n"
            "错误详情已写入安装目录下的 app_error.log。",
        )
        app.quit()

    sys.excepthook = handle_exception


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Metro Capture")
    app.setOrganizationName("Local Tools")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    icon_path = Path(__file__).resolve().parent / "app.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    install_exception_handler(app)

    initial_video = None
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.is_file():
            initial_video = str(candidate)

    window = MainWindow(initial_video)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
