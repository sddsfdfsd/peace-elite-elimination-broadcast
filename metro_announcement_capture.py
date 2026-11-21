#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
和平精英地铁逃生录屏播报截图工具（离线后处理版）

工作方式：
    1. 输入一个已经录好的本地视频。
    2. 从视频中取出一帧，弹出窗口，由用户鼠标框选播报区域。
    3. OpenCV 遍历视频，PaddleOCR 只检查所选区域是否存在文字。
    4. 文字出现时保存；持续有文字时，只有本轮与上一轮识别出的文字不同才保存。

隐私与安全：
    OCR 识别出的文字只在内存中生成哈希签名，用来比较前后两轮是否相同。
    脚本不会打印、保存或分析识别出的文字内容。
    脚本不读取游戏进程、不进行实时监控，也不包含点击或操控游戏的功能。

运行方式：
    py -3.11 metro_announcement_capture.py "D:\\Videos\\录屏.mp4"

如果不传视频路径，脚本会在终端中要求输入路径。
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

try:
    import cv2
    import numpy as np
except ImportError as exc:
    print(
        "错误：缺少 OpenCV 或 NumPy。请使用 Python 3.11 安装依赖：\n"
        "py -3.11 -m pip install -r requirements.txt\n"
        "随后安装 paddlepaddle 或 paddlepaddle-gpu。",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


# =============================================================================
# 用户配置区：通常不需要修改
# =============================================================================

# 也可以通过这里固定视频路径；留空时使用命令行参数或交互式输入。
DEFAULT_VIDEO_PATH = ""

# 每隔多少秒执行一次 OCR。默认 1 秒。
# 想减少漏掉短播报的概率，可以改小，例如 0.2；代价是处理更慢。
OCR_INTERVAL_SECONDS = 1.5

# OCR 识别置信度下限。低于该值的识别结果不算“检测到文字”。
MIN_TEXT_CONFIDENCE = 0.60

# 过滤尺寸过小的文字框，减少图标、噪点等造成的误判。
# 这两个尺寸对应放大后的 OCR 输入图。
MIN_TEXT_BOX_WIDTH = 8.0
MIN_TEXT_BOX_HEIGHT = 10.0

# 完全相同画面的感知去重阈值。视频压缩、背景动画和 OCR 轻微抖动都可能
# 让同一播报产生小差异；只有两种感知哈希都足够接近时才视为重复画面。
DEDUPE_DHASH_DISTANCE = 10
DEDUPE_PHASH_DISTANCE = 10
DEDUPE_CONTENT_PHASH_DISTANCE = 6
DEDUPE_LINE_LENGTH_RATIO_THRESHOLD = 0.05
DEDUPE_CHANGE_PIXEL_DIFF = 30
DEDUPE_CHANGE_MIN_AREA = 16

# 将框选区域放大后再交给 OCR，有助于识别录屏中的细小文字。
# 设为 1.0 表示不放大。
OCR_UPSCALE = 2.0

# PaddleOCR 语言模型。和平精英通常需要简体中文模型。
OCR_LANGUAGE = "ch"

# 使用 RTX 显卡进行批量推理。显卡不可用时 PaddleX 会自动回退到 CPU。
OCR_DEVICE = "gpu:0"
OCR_BATCH_SIZE = 8

# 输出文件夹后缀。最终目录位于视频同级。
OUTPUT_DIR_SUFFIX = "_播报截图"

# 视频 FPS 元数据异常时用于计算采样步长的备用值。
FALLBACK_FPS = 30.0

# 框选窗口相关设置。
# 初始画面取视频约 10% 位置的一帧；框选时可按 A/D 前后翻帧。
ROI_SELECTION_START_RATIO = 0.10
ROI_SELECTION_SEEK_SECONDS = 1.0
ROI_SELECTION_MAX_WIDTH = 1600
ROI_SELECTION_MAX_HEIGHT = 900
MIN_ROI_WIDTH = 16
MIN_ROI_HEIGHT = 8


class ScriptError(RuntimeError):
    """表示可以直接展示给用户的运行错误。"""


class ProcessingCancelled(RuntimeError):
    """表示用户主动取消了视频处理。"""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。视频路径是可选位置参数。"""
    parser = argparse.ArgumentParser(
        description=(
            "离线检查本地录屏中的播报区域，并在文字出现或文字内容变化时"
            "截取该区域的小图。"
        )
    )
    parser.add_argument(
        "video",
        nargs="?",
        default="",
        help='视频文件路径，例如 "D:\\Videos\\录屏.mp4"；省略时会提示输入。',
    )
    return parser.parse_args(argv)


def resolve_video_path(command_line_path: str) -> Path:
    """取得并校验视频路径，支持命令行、顶部常量以及交互输入。"""
    raw_path = command_line_path.strip() or DEFAULT_VIDEO_PATH.strip()

    if not raw_path:
        raw_path = input("请输入本地视频文件路径：").strip()

    # 用户从资源管理器拖入时，路径两端可能带有引号。
    raw_path = raw_path.strip().strip('"').strip("'").strip()
    if not raw_path:
        raise ScriptError("没有提供视频文件路径。")

    video_path = Path(raw_path).expanduser().resolve()
    if not video_path.is_file():
        raise ScriptError(f"视频文件不存在：{video_path}")
    return video_path


def validate_configuration() -> None:
    """在开始处理前检查数值配置。"""
    if not math.isfinite(OCR_INTERVAL_SECONDS) or OCR_INTERVAL_SECONDS <= 0:
        raise ScriptError("OCR_INTERVAL_SECONDS 必须大于 0。")
    if not 0.0 <= MIN_TEXT_CONFIDENCE <= 1.0:
        raise ScriptError("MIN_TEXT_CONFIDENCE 必须在 0.0 到 1.0 之间。")
    if OCR_UPSCALE <= 0:
        raise ScriptError("OCR_UPSCALE 必须大于 0。")
    if OCR_BATCH_SIZE <= 0:
        raise ScriptError("OCR_BATCH_SIZE 必须大于 0。")
    if MIN_TEXT_BOX_WIDTH < 0 or MIN_TEXT_BOX_HEIGHT < 0:
        raise ScriptError("文字框过滤尺寸不能小于 0。")
    if not 0 <= DEDUPE_DHASH_DISTANCE <= 256:
        raise ScriptError("DEDUPE_DHASH_DISTANCE 必须在 0 到 256 之间。")
    if not 0 <= DEDUPE_PHASH_DISTANCE <= 64:
        raise ScriptError("DEDUPE_PHASH_DISTANCE 必须在 0 到 64 之间。")
    if not 0 <= DEDUPE_CONTENT_PHASH_DISTANCE <= 64:
        raise ScriptError("DEDUPE_CONTENT_PHASH_DISTANCE 必须在 0 到 64 之间。")
    if not 0.0 <= DEDUPE_LINE_LENGTH_RATIO_THRESHOLD <= 1.0:
        raise ScriptError(
            "DEDUPE_LINE_LENGTH_RATIO_THRESHOLD 必须在 0.0 到 1.0 之间。"
        )
    if not 0 <= DEDUPE_CHANGE_PIXEL_DIFF <= 255:
        raise ScriptError("DEDUPE_CHANGE_PIXEL_DIFF 必须在 0 到 255 之间。")
    if DEDUPE_CHANGE_MIN_AREA <= 0:
        raise ScriptError("DEDUPE_CHANGE_MIN_AREA 必须大于 0。")
    if not 0.0 <= ROI_SELECTION_START_RATIO <= 1.0:
        raise ScriptError("ROI_SELECTION_START_RATIO 必须在 0.0 到 1.0 之间。")
    if ROI_SELECTION_SEEK_SECONDS <= 0:
        raise ScriptError("ROI_SELECTION_SEEK_SECONDS 必须大于 0。")


def open_video(video_path: Path) -> cv2.VideoCapture:
    """打开视频，并在失败时给出明确提示。"""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise ScriptError(
            f"OpenCV 无法打开视频：{video_path}\n"
            "请确认文件未损坏，并确认 OpenCV 支持该视频编码格式。"
        )
    return capture


def read_video_info(capture: cv2.VideoCapture) -> tuple[int, int, float, int]:
    """读取视频宽、高、FPS 和帧数。"""
    width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))

    if width <= 0 or height <= 0:
        raise ScriptError("无法读取视频分辨率，视频可能已损坏或编码不受支持。")
    return width, height, fps, frame_count


def inspect_video(video_path: Path) -> tuple[int, int, float, int]:
    """快速检查视频并返回基本信息。"""
    capture = open_video(video_path)
    try:
        return read_video_info(capture)
    finally:
        capture.release()


def validate_roi(
    roi: Sequence[int],
    frame_width: int,
    frame_height: int,
) -> tuple[int, int, int, int]:
    """验证鼠标框选结果是否有效。"""
    if len(roi) != 4:
        raise ScriptError("框选区域必须包含四个坐标值。")

    try:
        x1, y1, x2, y2 = (int(value) for value in roi)
    except (TypeError, ValueError) as exc:
        raise ScriptError("框选区域坐标无效。") from exc

    if (
        x1 < 0
        or y1 < 0
        or x2 > frame_width
        or y2 > frame_height
        or x2 <= x1
        or y2 <= y1
    ):
        raise ScriptError(
            "框选区域超出视频画面，或框选区域为空。\n"
            f"当前视频分辨率：{frame_width} x {frame_height}"
        )

    if x2 - x1 < MIN_ROI_WIDTH or y2 - y1 < MIN_ROI_HEIGHT:
        raise ScriptError(
            f"框选区域太小，宽度至少 {MIN_ROI_WIDTH} 像素、"
            f"高度至少 {MIN_ROI_HEIGHT} 像素。"
        )

    return x1, y1, x2, y2


def _seek_and_read_frame(
    capture: cv2.VideoCapture,
    frame_index: int,
    frame_count: int,
) -> tuple[int, np.ndarray]:
    """跳转到指定帧并读取画面。"""
    if frame_count > 0:
        frame_index = max(0, min(frame_count - 1, frame_index))
    else:
        frame_index = max(0, frame_index)

    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    success, frame = capture.read()
    if not success or frame is None:
        # 如果 seek 失败，再尝试读取第一帧。
        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        success, frame = capture.read()
        frame_index = 0

    if not success or frame is None:
        raise ScriptError("无法从视频中读取可供框选的画面。")
    return frame_index, frame


def _display_scale(width: int, height: int) -> float:
    """计算框选窗口的显示缩放比例，避免 4K 视频窗口过大。"""
    return min(
        1.0,
        ROI_SELECTION_MAX_WIDTH / max(1, width),
        ROI_SELECTION_MAX_HEIGHT / max(1, height),
    )


def select_roi_interactively(
    video_path: Path,
) -> tuple[int, int, int, int]:
    """
    打开视频并弹出鼠标框选窗口。

    操作：
        按住鼠标左键拖动：框选播报区域
        Enter 或空格：确认当前框选
        A / D：向前 / 向后翻 1 秒，便于找到出现播报的画面
        C 或 Esc：取消
    """
    capture = open_video(video_path)
    width, height, fps, frame_count = read_video_info(capture)
    effective_fps = fps if math.isfinite(fps) and fps > 0 else FALLBACK_FPS

    initial_index = (
        min(frame_count - 1, int(frame_count * ROI_SELECTION_START_RATIO))
        if frame_count > 0
        else 0
    )
    current_index, frame = _seek_and_read_frame(
        capture,
        initial_index,
        frame_count,
    )

    window_name = "Select announcement area"
    instruction = (
        "Drag with left mouse button | Enter/Space: confirm | "
        "A/D: seek 1 second | C/Esc: cancel"
    )

    selection: tuple[int, int, int, int] | None = None
    drag_start: tuple[int, int] | None = None

    try:
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    except cv2.error as exc:
        capture.release()
        raise ScriptError(
            "无法创建框选窗口。本脚本需要桌面图形界面，"
            "不能在无窗口的服务器环境中运行。"
        ) from exc

    def display_to_source(
        x: int,
        y: int,
        scale: float,
    ) -> tuple[int, int]:
        source_x = max(0, min(width - 1, int(round(x / scale))))
        source_y = max(0, min(height - 1, int(round(y / scale))))
        return source_x, source_y

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: Any) -> None:
        nonlocal selection, drag_start

        current_scale = _display_scale(width, height)
        source_x, source_y = display_to_source(x, y, current_scale)

        if event == cv2.EVENT_LBUTTONDOWN:
            drag_start = (source_x, source_y)
            selection = (source_x, source_y, source_x, source_y)
        elif event == cv2.EVENT_MOUSEMOVE and drag_start is not None:
            start_x, start_y = drag_start
            left, right = sorted((start_x, source_x))
            top, bottom = sorted((start_y, source_y))
            selection = (left, top, right, bottom)
        elif event == cv2.EVENT_LBUTTONUP and drag_start is not None:
            start_x, start_y = drag_start
            left, right = sorted((start_x, source_x))
            top, bottom = sorted((start_y, source_y))
            if (
                right - left >= MIN_ROI_WIDTH
                and bottom - top >= MIN_ROI_HEIGHT
            ):
                selection = (left, top, right, bottom)
            else:
                selection = None
            drag_start = None

    cv2.setMouseCallback(window_name, on_mouse)

    def redraw() -> None:
        canvas = frame.copy()
        if selection is not None:
            x1, y1, x2, y2 = selection
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)

        scale = _display_scale(width, height)
        display = (
            cv2.resize(
                canvas,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_AREA,
            )
            if scale < 1.0
            else canvas
        )

        # 在缩放后的画面上绘制提示，保证高分辨率录屏中的文字仍清楚可见。
        cv2.putText(
            display,
            instruction,
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.imshow(window_name, display)

    try:
        print("请在弹出的窗口里按住鼠标左键框选播报区域。")
        print("A / D 键可前后翻 1 秒寻找出现了播报的画面。")
        print("框选后按 Enter 或空格确认；按 C 或 Esc 取消。")

        while True:
            redraw()

            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                raise ScriptError("框选窗口已关闭，未取得检测区域。")

            key = cv2.waitKeyEx(20)

            if key in (13, 32):  # Enter / 空格
                if selection is None:
                    print("还没有有效框选，请先按住鼠标左键拖动。")
                    continue
                return validate_roi(selection, width, height)

            if key in (27, ord("c"), ord("C")):
                raise ScriptError("已取消框选。")

            if key in (ord("a"), ord("A"), 2424832):
                seek_delta = -max(1, int(round(effective_fps * ROI_SELECTION_SEEK_SECONDS)))
                current_index = max(0, current_index + seek_delta)
                current_index, frame = _seek_and_read_frame(
                    capture,
                    current_index,
                    frame_count,
                )
                selection = None
                drag_start = None

            if key in (ord("d"), ord("D"), 2555904):
                seek_delta = max(1, int(round(effective_fps * ROI_SELECTION_SEEK_SECONDS)))
                target_index = current_index + seek_delta
                if frame_count > 0:
                    target_index = min(frame_count - 1, target_index)
                current_index, frame = _seek_and_read_frame(
                    capture,
                    target_index,
                    frame_count,
                )
                selection = None
                drag_start = None
    finally:
        capture.release()
        try:
            cv2.destroyWindow(window_name)
        except cv2.error:
            pass
        cv2.waitKey(1)


def create_ocr() -> Any:
    """创建并复用 PaddleOCR 实例。"""
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise ScriptError(
            "缺少 PaddleOCR 或 PaddlePaddle。\n"
            "请使用 Python 3.11 安装依赖：\n"
            "py -3.11 -m pip install paddlepaddle==3.3.1 "
            "paddleocr==3.7.0 opencv-contrib-python==4.10.0.84"
        ) from exc

    try:
        return PaddleOCR(
            lang=OCR_LANGUAGE,
            device=OCR_DEVICE,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_recognition_batch_size=OCR_BATCH_SIZE,
            # GPU 默认不使用 oneDNN；关闭它也可保证 CPU 回退时稳定运行。
            enable_mkldnn=False,
        )
    except Exception as exc:
        raise ScriptError(
            "PaddleOCR 初始化失败。请确认依赖版本兼容。\n"
            f"原始错误：{type(exc).__name__}: {exc}"
        ) from exc


def _get_ocr_field(payload: Any, field_name: str) -> Any:
    """从不同 PaddleOCR 结果对象或字典中读取一个字段。"""
    value: Any = None

    if isinstance(payload, dict):
        value = payload.get(field_name)
    else:
        getter = getattr(payload, "get", None)
        if callable(getter):
            try:
                value = getter(field_name)
            except (KeyError, TypeError):
                value = None
        if value is None:
            value = getattr(payload, field_name, None)

    if callable(value):
        value = value()
    return value


def _iter_ocr_payloads(raw_results: Any) -> Iterator[Any]:
    """
    生成 OCR 结果中的内部字典。

    PaddleOCR 3.x 通常返回可迭代结果对象，其 .json 属性通常为
    {"res": {...}} 结构。兼容这些形式，但不向外部暴露识别文字。
    """
    if raw_results is None:
        return

    if isinstance(raw_results, dict):
        yield raw_results.get("res", raw_results)
        return

    try:
        items: Iterable[Any] = iter(raw_results)
    except TypeError:
        items = (raw_results,)

    for item in items:
        payload = item
        json_data = getattr(item, "json", None)
        if callable(json_data):
            json_data = json_data()

        if isinstance(json_data, dict):
            payload = json_data.get("res", json_data)
        yield payload


def _as_sequence(value: Any) -> Sequence[Any]:
    """将列表、元组或 NumPy 数组统一成可索引序列。"""
    if value is None:
        return ()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return value
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _box_dimensions(box: Any) -> tuple[float, float] | None:
    """计算 OCR 文字框的宽和高；无法确定时返回 None。"""
    try:
        points = np.asarray(box, dtype=float)
    except (TypeError, ValueError):
        return None

    if points.size < 4 or not np.all(np.isfinite(points)):
        return None

    if points.size == 4:
        flat = points.reshape(4)
        return (
            abs(float(flat[2] - flat[0])),
            abs(float(flat[3] - flat[1])),
        )

    if points.ndim == 2 and points.shape[1] == 2:
        return (
            float(points[:, 0].max() - points[:, 0].min()),
            float(points[:, 1].max() - points[:, 1].min()),
        )
    return None


def ocr_results_text_signature(raw_results: Any) -> str | None:
    """
    根据 OCR 结果生成文字签名。

    文字只在函数内部读取，并立即转换为 SHA-256 哈希。
    外部状态只保存哈希，不保存文字，也不能从哈希恢复原文。
    返回 None 表示本轮没有达到阈值的文字。
    """
    recognized_parts: list[str] = []

    for payload in _iter_ocr_payloads(raw_results):
        texts = _as_sequence(_get_ocr_field(payload, "rec_texts"))
        if not texts:
            continue

        scores = _as_sequence(_get_ocr_field(payload, "rec_scores"))
        boxes = _as_sequence(_get_ocr_field(payload, "rec_boxes"))

        for index, text in enumerate(texts):
            if text is None:
                continue

            try:
                text_value = str(text)
            except Exception:
                continue

            # 只移除空白，避免同一文字因空格位置变化而反复触发。
            normalized_text = "".join(text_value.split())
            if not normalized_text:
                continue

            try:
                confidence = (
                    float(scores[index]) if index < len(scores) else 0.0
                )
            except (TypeError, ValueError, OverflowError):
                confidence = 0.0

            if not math.isfinite(confidence) or confidence < MIN_TEXT_CONFIDENCE:
                continue

            if index < len(boxes):
                dimensions = _box_dimensions(boxes[index])
                if dimensions is not None:
                    box_width, box_height = dimensions
                    if (
                        box_width < MIN_TEXT_BOX_WIDTH
                        or box_height < MIN_TEXT_BOX_HEIGHT
                    ):
                        continue

            recognized_parts.append(normalized_text)

    if not recognized_parts:
        return None

    # 直接连接各识别行，减少 OCR 分行位置变化造成的非文字内容差异。
    joined_text = "".join(recognized_parts)
    return hashlib.sha256(joined_text.encode("utf-8")).hexdigest()


def _recognized_text_parts(raw_results: Any) -> tuple[str, ...]:
    """提取用于内部比较的规范化文字片段，不向界面或文件暴露原文。"""
    recognized_parts: list[str] = []

    for payload in _iter_ocr_payloads(raw_results):
        texts = _as_sequence(_get_ocr_field(payload, "rec_texts"))
        if not texts:
            continue

        scores = _as_sequence(_get_ocr_field(payload, "rec_scores"))
        boxes = _as_sequence(_get_ocr_field(payload, "rec_boxes"))

        for index, text in enumerate(texts):
            if text is None:
                continue
            try:
                text_value = str(text)
            except Exception:
                continue

            normalized_text = "".join(text_value.split())
            if not normalized_text:
                continue

            try:
                confidence = (
                    float(scores[index]) if index < len(scores) else 0.0
                )
            except (TypeError, ValueError, OverflowError):
                confidence = 0.0

            if not math.isfinite(confidence) or confidence < MIN_TEXT_CONFIDENCE:
                continue

            if index < len(boxes):
                dimensions = _box_dimensions(boxes[index])
                if dimensions is not None:
                    box_width, box_height = dimensions
                    if (
                        box_width < MIN_TEXT_BOX_WIDTH
                        or box_height < MIN_TEXT_BOX_HEIGHT
                    ):
                        continue

            recognized_parts.append(normalized_text)

    return tuple(recognized_parts)


def _recognized_text_line_width(raw_results: Any) -> float | None:
    """计算本轮有效 OCR 文字框的整行水平跨度。"""
    left: float | None = None
    right: float | None = None

    for payload in _iter_ocr_payloads(raw_results):
        texts = _as_sequence(_get_ocr_field(payload, "rec_texts"))
        scores = _as_sequence(_get_ocr_field(payload, "rec_scores"))
        boxes = _as_sequence(_get_ocr_field(payload, "rec_boxes"))

        for index, text in enumerate(texts):
            if text is None or not str(text).strip():
                continue
            try:
                confidence = (
                    float(scores[index]) if index < len(scores) else 0.0
                )
            except (TypeError, ValueError, OverflowError):
                confidence = 0.0
            if not math.isfinite(confidence) or confidence < MIN_TEXT_CONFIDENCE:
                continue
            if index >= len(boxes):
                continue

            box = boxes[index]
            dimensions = _box_dimensions(box)
            if dimensions is None:
                continue
            box_width, box_height = dimensions
            if (
                box_width < MIN_TEXT_BOX_WIDTH
                or box_height < MIN_TEXT_BOX_HEIGHT
            ):
                continue

            try:
                points = np.asarray(box, dtype=float)
            except (TypeError, ValueError):
                continue

            if points.size == 4:
                x_values = points.reshape(4)[[0, 2]]
            elif points.ndim == 2 and points.shape[1] == 2:
                x_values = points[:, 0]
            else:
                continue

            box_left = float(np.min(x_values))
            box_right = float(np.max(x_values))
            left = box_left if left is None else min(left, box_left)
            right = box_right if right is None else max(right, box_right)

    if left is None or right is None or right <= left:
        return None
    return right - left


def ocr_results_text_observation(
    raw_results: Any,
) -> tuple[str | None, tuple[str, ...], float | None]:
    """同时返回文字哈希和仅供内部去重使用的规范化片段。"""
    parts = _recognized_text_parts(raw_results)
    if not parts:
        return None, (), None
    signature = hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()
    return signature, parts, _recognized_text_line_width(raw_results)


def _canonical_ocr_part(part: str) -> str:
    """去掉标点和符号，保留中英文、数字。"""
    return "".join(character for character in part if character.isalnum())


def ocr_parts_are_equivalent(
    current_parts: tuple[str, ...],
    previous_parts: tuple[str, ...],
) -> bool:
    """
    判断两轮 OCR 片段是否只是轻微识别抖动。

    三个字符及以下的短片段必须完全一致，避免把不同的短名字误去重。
    较长片段允许一个字符左右的识别差异。
    """
    current = tuple(
        value
        for value in (_canonical_ocr_part(part) for part in current_parts)
        if value
    )
    previous = tuple(
        value
        for value in (_canonical_ocr_part(part) for part in previous_parts)
        if value
    )

    if not current or not previous:
        return False
    if current == previous:
        return True

    if len(current) == len(previous):
        for current_part, previous_part in zip(current, previous):
            if current_part == previous_part:
                continue
            if min(len(current_part), len(previous_part)) <= 3:
                return False
            if abs(len(current_part) - len(previous_part)) > 1:
                return False
            similarity = SequenceMatcher(
                None,
                current_part,
                previous_part,
            ).ratio()
            if similarity < 0.80:
                return False
        return True

    current_joined = "".join(current)
    previous_joined = "".join(previous)
    if abs(len(current_joined) - len(previous_joined)) > 2:
        return False
    return (
        SequenceMatcher(None, current_joined, previous_joined).ratio()
        >= 0.93
    )


def short_player_tokens(parts: tuple[str, ...]) -> tuple[str, ...]:
    """提取内部用于保护玩家名变化的 2-3 字中文短片段。"""
    tokens: list[str] = []
    for part in parts:
        canonical = _canonical_ocr_part(part)
        if 2 <= len(canonical) <= 3 and canonical.isalnum():
            tokens.append(canonical)
    return tuple(sorted(tokens))


def short_player_tokens_compatible(
    current_parts: tuple[str, ...],
    previous_parts: tuple[str, ...],
) -> bool:
    """
    短中文名字存在时必须完全一致。

    如果某一轮没有提取到短名字，则交由内容指纹决定是否去重。
    """
    current = short_player_tokens(current_parts)
    previous = short_player_tokens(previous_parts)
    if not current or not previous:
        return True
    return current == previous


def stable_text_identity_key(
    parts: tuple[str, ...],
    line_length: float | None,
) -> str:
    """
    为“同一行文字”生成稳定身份键。

    优先使用 2-3 字中文/英文玩家名，忽略单字符图标噪音；没有短名字时
    使用所有有效字母数字片段。再结合文字行长度分桶，使 OCR 分行变化
    不会把同一行误当成新文字。
    """
    tokens = short_player_tokens(parts)
    if not tokens:
        tokens = tuple(
            sorted(
                value
                for value in (
                    _canonical_ocr_part(part)
                    for part in parts
                )
                if len(value) >= 2
            )
        )

    if not tokens:
        tokens = tuple(
            sorted(
                value
                for value in (
                    _canonical_ocr_part(part)
                    for part in parts
                )
                if value
            )
        )

    # 同一行文字的身份只由有效文字片段决定，不再受 OCR 框长度抖动影响。
    identity = "|".join(tokens)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def detect_text_signature(
    ocr: Any,
    roi_bgr: np.ndarray,
) -> str | None:
    """放大播报区域并执行 OCR，只返回文字签名或 None。"""
    return detect_text_signatures(ocr, [roi_bgr])[0]


def detect_text_signatures(
    ocr: Any,
    roi_images: Sequence[np.ndarray],
) -> list[str | None]:
    """批量执行 OCR，同时仍为每个一秒采样点保留独立结果。"""
    if not roi_images:
        return []

    ocr_inputs: list[np.ndarray] = []
    for roi_bgr in roi_images:
        if OCR_UPSCALE != 1.0:
            ocr_inputs.append(
                cv2.resize(
                    roi_bgr,
                    None,
                    fx=OCR_UPSCALE,
                    fy=OCR_UPSCALE,
                    interpolation=cv2.INTER_CUBIC,
                )
            )
        else:
            ocr_inputs.append(roi_bgr)

    try:
        raw_results = ocr.predict(ocr_inputs)
    except Exception as exc:
        raise ScriptError(
            "PaddleOCR 批量识别当前区域时失败。\n"
            f"原始错误：{type(exc).__name__}: {exc}"
        ) from exc

    results = list(raw_results)
    if len(results) != len(ocr_inputs):
        raise ScriptError(
            "OCR 批量结果数量与输入帧数量不一致，已停止处理以避免错位。"
        )

    return [ocr_results_text_signature([result]) for result in results]


def detect_text_observations(
    ocr: Any,
    roi_images: Sequence[np.ndarray],
) -> list[tuple[str | None, tuple[str, ...], float | None]]:
    """批量 OCR，并返回文字哈希和内部去重片段。"""
    if not roi_images:
        return []

    ocr_inputs: list[np.ndarray] = []
    for roi_bgr in roi_images:
        if OCR_UPSCALE != 1.0:
            ocr_inputs.append(
                cv2.resize(
                    roi_bgr,
                    None,
                    fx=OCR_UPSCALE,
                    fy=OCR_UPSCALE,
                    interpolation=cv2.INTER_CUBIC,
                )
            )
        else:
            ocr_inputs.append(roi_bgr)

    try:
        raw_results = ocr.predict(ocr_inputs)
    except Exception as exc:
        raise ScriptError(
            "PaddleOCR 批量识别当前区域时失败。\n"
            f"原始错误：{type(exc).__name__}: {exc}"
        ) from exc

    results = list(raw_results)
    if len(results) != len(ocr_inputs):
        raise ScriptError(
            "OCR 批量结果数量与输入帧数量不一致，已停止处理以避免错位。"
        )

    return [ocr_results_text_observation([result]) for result in results]


def reserve_event_directory(output_root: Path) -> Path:
    """在输出根目录中创建一个未使用的 event_XXXX 目录。"""
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScriptError(f"无法创建输出目录：{output_root}\n{exc}") from exc

    event_index = 1
    while True:
        event_dir = output_root / f"event_{event_index:04d}"
        try:
            event_dir.mkdir(exist_ok=False)
            return event_dir
        except FileExistsError:
            event_index += 1
        except OSError as exc:
            raise ScriptError(f"无法创建事件目录：{event_dir}\n{exc}") from exc


def next_capture_path(event_dir: Path) -> Path:
    """获取下一个不会覆盖旧截图的文件名。"""
    image_index = 1
    while True:
        image_path = event_dir / f"{image_index:03d}.png"
        if not image_path.exists():
            return image_path
        image_index += 1


def save_roi_image(roi_bgr: np.ndarray, event_dir: Path) -> Path:
    """使用 OpenCV 编码并通过 Python 写文件，兼容中文路径。"""
    image_path = next_capture_path(event_dir)
    success, encoded = cv2.imencode(".png", roi_bgr)
    if not success:
        raise ScriptError(f"OpenCV 无法把截图编码为 PNG：{image_path}")

    try:
        encoded.tofile(str(image_path))
    except OSError as exc:
        raise ScriptError(f"无法保存截图：{image_path}\n{exc}") from exc
    return image_path


def image_content_signature(roi_bgr: np.ndarray) -> str:
    """
    生成截图内容的精确哈希。

    只有解码后像素完全相同的小图才会得到相同签名。
    该签名用于保存前去重，不参与判断文字或画面是否变化。
    """
    contiguous = np.ascontiguousarray(roi_bgr)
    hasher = hashlib.sha256()
    hasher.update(str(contiguous.shape).encode("ascii"))
    hasher.update(contiguous.tobytes())
    return hasher.hexdigest()


def collect_existing_image_signatures(
    output_root: Path | None,
) -> tuple[
    set[str],
    list[tuple[bytes, bytes]],
    list[np.ndarray],
    list[bytes],
]:
    """读取已有截图签名，避免重复运行同一视频时再次保存相同画面。"""
    existing: set[str] = set()
    existing_features: list[tuple[bytes, bytes]] = []
    existing_references: list[np.ndarray] = []
    existing_content_features: list[bytes] = []
    if output_root is None or not output_root.exists():
        return (
            existing,
            existing_features,
            existing_references,
            existing_content_features,
        )

    for image_path in output_root.rglob("*.png"):
        try:
            encoded = np.fromfile(str(image_path), dtype=np.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        except (OSError, cv2.error):
            continue
        if image is not None:
            existing.add(image_content_signature(image))
            existing_features.append(image_perceptual_signature(image))
            existing_references.append(prepare_visual_reference(image))
            existing_content_features.append(image_content_phash(image))
    return (
        existing,
        existing_features,
        existing_references,
        existing_content_features,
    )


def image_perceptual_signature(
    roi_bgr: np.ndarray,
) -> tuple[bytes, bytes]:
    """生成 dHash 与 pHash；用于抵抗压缩噪声和轻微背景变化。"""
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

    dhash_image = cv2.resize(
        gray,
        (17, 16),
        interpolation=cv2.INTER_AREA,
    )
    dhash_bits = (dhash_image[:, 1:] > dhash_image[:, :-1]).reshape(-1)
    dhash_bytes = np.packbits(dhash_bits).tobytes()

    phash_image = cv2.resize(
        gray,
        (32, 32),
        interpolation=cv2.INTER_AREA,
    )
    dct = cv2.dct(phash_image.astype(np.float32))
    low_frequency = dct[:8, :8].reshape(-1)
    phash_bits = (
        low_frequency > float(np.median(low_frequency))
    ).astype(np.uint8)
    phash_bytes = np.packbits(phash_bits).tobytes()
    return dhash_bytes, phash_bytes


def image_content_phash(roi_bgr: np.ndarray) -> bytes:
    """
    只对高对比度的文字和图标生成 pHash。

    顶帽变换抑制大块背景纹理，突出白字和小图标，使同一播报在背景轻微
    变化时仍得到接近的内容指纹，而新增叉号等图标会明显改变该指纹。
    """
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    tophat = cv2.morphologyEx(
        gray,
        cv2.MORPH_TOPHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)),
    )
    content_mask = (tophat >= 18).astype(np.uint8) * 255
    resized = cv2.resize(
        content_mask,
        (32, 32),
        interpolation=cv2.INTER_AREA,
    )
    dct = cv2.dct(resized.astype(np.float32))
    low_frequency = dct[:8, :8].reshape(-1)
    bits = (
        low_frequency > float(np.median(low_frequency))
    ).astype(np.uint8)
    return np.packbits(bits).tobytes()


def is_near_identical_image(
    current_features: tuple[bytes, bytes],
    previous_features: tuple[bytes, bytes],
) -> bool:
    """同时比较 dHash 与 pHash，任一指纹明显不同就不去重。"""
    current_dhash, current_phash = current_features
    previous_dhash, previous_phash = previous_features

    dhash_distance = (
        int.from_bytes(current_dhash, "big")
        ^ int.from_bytes(previous_dhash, "big")
    ).bit_count()
    phash_distance = (
        int.from_bytes(current_phash, "big")
        ^ int.from_bytes(previous_phash, "big")
    ).bit_count()

    return (
        dhash_distance <= DEDUPE_DHASH_DISTANCE
        and phash_distance <= DEDUPE_PHASH_DISTANCE
    )


def phash_hamming_distance(
    current_features: tuple[bytes, bytes],
    previous_features: tuple[bytes, bytes],
) -> int:
    """计算 pHash 汉明距离；对背景细节和裁切对齐更稳定。"""
    _current_dhash, current_phash = current_features
    _previous_dhash, previous_phash = previous_features
    return (
        int.from_bytes(current_phash, "big")
        ^ int.from_bytes(previous_phash, "big")
    ).bit_count()


def content_phash_hamming_distance(
    current_content_hash: bytes,
    previous_content_hash: bytes,
) -> int:
    """计算文字/图标内容指纹的汉明距离。"""
    return (
        int.from_bytes(current_content_hash, "big")
        ^ int.from_bytes(previous_content_hash, "big")
    ).bit_count()


def prepare_visual_reference(roi_bgr: np.ndarray) -> np.ndarray:
    """生成去重比较用的灰度参考图，限制宽度以控制内存占用。"""
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] > 900:
        scale = 900 / gray.shape[1]
        gray = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )
    return gray


def has_meaningful_visual_change(
    current_reference: np.ndarray,
    previous_reference: np.ndarray,
) -> bool:
    """
    检查是否有成块的明显视觉变化。

    视频压缩噪点通常只是零散小点；新增叉号、武器图标等会形成足够大的
    连续差异区域，因此应保留为一张新截图。
    """
    if current_reference.shape != previous_reference.shape:
        return True

    current_blur = cv2.GaussianBlur(current_reference, (3, 3), 0)
    previous_blur = cv2.GaussianBlur(previous_reference, (3, 3), 0)
    difference = cv2.absdiff(current_blur, previous_blur)
    mask = (difference >= DEDUPE_CHANGE_PIXEL_DIFF).astype(np.uint8)
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        np.ones((3, 3), dtype=np.uint8),
    )

    component_count, _labels, stats, _centroids = (
        cv2.connectedComponentsWithStats(mask, connectivity=8)
    )
    if component_count <= 1:
        return False

    largest_area = int(
        np.max(stats[1:, cv2.CC_STAT_AREA])
    )
    return largest_area >= DEDUPE_CHANGE_MIN_AREA


def calculate_frame_step(fps: float) -> int:
    """根据 FPS 和 OCR 间隔计算采样步长。"""
    effective_fps = fps if math.isfinite(fps) and fps > 0 else FALLBACK_FPS
    return max(1, int(round(effective_fps * OCR_INTERVAL_SECONDS)))


def process_video(
    video_path: Path,
    output_root: Path | None,
    ocr: Any,
    roi: Sequence[int],
    capture_callback: (
        Callable[[int, int, np.ndarray, str], None] | None
    ) = None,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[int, int, int]:
    """
    遍历视频并按文字状态保存截图。

    返回：(播报事件数, 保存截图数, OCR 采样次数)
    """
    capture = open_video(video_path)
    try:
        width, height, fps, frame_count = read_video_info(capture)
        x1, y1, x2, y2 = validate_roi(roi, width, height)
        frame_step = calculate_frame_step(fps)
        total_samples = (
            math.ceil(frame_count / frame_step) if frame_count > 0 else 0
        )

        event_count = 0
        saved_count = 0
        sampled_count = 0
        frame_index = 0
        text_present_before = False
        previous_text_signature: str | None = None
        current_event_dir: Path | None = None
        event_capture_count = 0
        progress_interval = max(1, int(round(30.0 / OCR_INTERVAL_SECONDS)))
        pending_rois: list[np.ndarray] = []
        (
            known_image_signatures,
            known_image_samples,
            known_visual_references,
            known_content_features,
        ) = collect_existing_image_signatures(output_root)
        current_event_text_parts: list[tuple[str, ...]] = []
        current_event_visual_references: list[np.ndarray] = []
        current_event_image_features: list[tuple[bytes, bytes]] = []
        current_event_content_features: list[bytes] = []
        current_event_line_lengths: list[float] = []
        known_line_lengths: list[float | None] = [
            None for _ in known_image_samples
        ]
        identity_buckets: list[
            tuple[float, tuple[str, ...], str]
        ] = []

        def capture_identity_key(
            parts: tuple[str, ...],
            line_length: float | None,
        ) -> str:
            for previous_length, previous_parts, key in identity_buckets:
                if ocr_parts_are_equivalent(parts, previous_parts):
                    return key

                if line_length is not None and previous_length > 0:
                    current_short_tokens = short_player_tokens(parts)
                    previous_short_tokens = short_player_tokens(previous_parts)
                    relative_change = abs(
                        line_length - previous_length
                    ) / max(
                        1.0,
                        line_length,
                        previous_length,
                    )
                    if (
                        relative_change
                        <= DEDUPE_LINE_LENGTH_RATIO_THRESHOLD
                        and current_short_tokens
                        and previous_short_tokens
                        and short_player_tokens_compatible(
                            parts,
                            previous_parts,
                        )
                    ):
                        return key

            key = stable_text_identity_key(parts, line_length)
            identity_buckets.append(
                (
                    line_length if line_length is not None else 0.0,
                    parts,
                    key,
                )
            )
            return key

        def report_capture(
            roi_bgr: np.ndarray,
            text_parts: tuple[str, ...],
            line_length: float | None,
            text_signature: str,
            allow_text_dedupe: bool,
        ) -> bool:
            nonlocal event_capture_count, current_event_dir

            # 界面结果不在这里做文本去重：每个候选都交给界面，
            # 由界面按文字签名只保留最后一次出现。
            if capture_callback is not None:
                event_capture_count += 1
                capture_callback(
                    event_count,
                    event_capture_count,
                    roi_bgr.copy(),
                    capture_identity_key(text_parts, line_length),
                )
                return True

            if line_length is not None:
                reference_lengths = (
                    current_event_line_lengths
                    if allow_text_dedupe
                    else known_line_lengths
                )
                for previous_length in reference_lengths:
                    if previous_length is None:
                        continue
                    relative_change = abs(line_length - previous_length) / max(
                        1.0,
                        line_length,
                        previous_length,
                    )
                    if (
                        relative_change
                        <= DEDUPE_LINE_LENGTH_RATIO_THRESHOLD
                    ):
                        return False

            current_reference = prepare_visual_reference(roi_bgr)
            image_features = image_perceptual_signature(roi_bgr)
            current_content_hash = image_content_phash(roi_bgr)
            equivalent_indices: list[int] = []
            if allow_text_dedupe:
                for index, previous_parts in enumerate(
                    current_event_text_parts
                ):
                    content_distance = content_phash_hamming_distance(
                        current_content_hash,
                        current_event_content_features[index],
                    )
                    if (
                        content_distance
                        <= DEDUPE_CONTENT_PHASH_DISTANCE
                        and short_player_tokens_compatible(
                            text_parts,
                            previous_parts,
                        )
                    ):
                        return False

                    if ocr_parts_are_equivalent(text_parts, previous_parts):
                        equivalent_indices.append(index)
                        if not has_meaningful_visual_change(
                            current_reference,
                            current_event_visual_references[index],
                        ):
                            return False

            # 去重放在真正触发保存之前：像素完全相同的截图只保留一次。
            image_signature = image_content_signature(roi_bgr)
            if image_signature in known_image_signatures:
                return False

            if not allow_text_dedupe or equivalent_indices:
                for index, previous_features in enumerate(
                    known_image_samples
                ):
                    if (
                        content_phash_hamming_distance(
                            current_content_hash,
                            known_content_features[index],
                        )
                        <= DEDUPE_CONTENT_PHASH_DISTANCE
                    ):
                        return False
                    if (
                        is_near_identical_image(
                            image_features,
                            previous_features,
                        )
                        and not has_meaningful_visual_change(
                            current_reference,
                            known_visual_references[index],
                        )
                    ):
                        return False

            known_image_signatures.add(image_signature)
            known_image_samples.append(image_features)
            known_visual_references.append(current_reference)
            known_content_features.append(current_content_hash)
            current_event_text_parts.append(text_parts)
            current_event_visual_references.append(current_reference)
            current_event_image_features.append(image_features)
            current_event_content_features.append(current_content_hash)
            if line_length is not None:
                current_event_line_lengths.append(line_length)
                known_line_lengths.append(line_length)
            else:
                known_line_lengths.append(None)
            event_capture_count += 1

            if output_root is not None:
                try:
                    output_root.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise ScriptError(
                        f"无法创建输出目录：{output_root}\n{exc}"
                    ) from exc
                save_roi_image(roi_bgr, output_root)
            return True

        def apply_signature(
            roi_bgr: np.ndarray,
            signature_now: str | None,
            text_parts_now: tuple[str, ...],
            line_length_now: float | None,
        ) -> None:
            nonlocal event_count, saved_count, sampled_count
            nonlocal text_present_before, previous_text_signature
            nonlocal current_event_dir, event_capture_count

            text_present_now = signature_now is not None

            if text_present_now:
                if not text_present_before:
                    # 从空白进入文字：新开一段连续播报，并保存第一张。
                    event_count += 1
                    current_event_dir = None
                    event_capture_count = 0
                    current_event_text_parts.clear()
                    current_event_visual_references.clear()
                    current_event_image_features.clear()
                    current_event_content_features.clear()
                    current_event_line_lengths.clear()
                    if report_capture(
                        roi_bgr,
                        text_parts_now,
                        line_length_now,
                        signature_now,
                        False,
                    ):
                        saved_count += 1
                elif signature_now != previous_text_signature:
                    # 本轮文字与上一秒不同：立即保存，不比较像素。
                    if report_capture(
                        roi_bgr,
                        text_parts_now,
                        line_length_now,
                        signature_now,
                        True,
                    ):
                        saved_count += 1
            elif text_present_before:
                # 文字变回空白：不保存，仅关闭当前播报事件。
                current_event_dir = None
                event_capture_count = 0
                current_event_text_parts.clear()
                current_event_visual_references.clear()
                current_event_image_features.clear()
                current_event_content_features.clear()
                current_event_line_lengths.clear()

            previous_text_signature = signature_now
            text_present_before = text_present_now
            sampled_count += 1

            if progress_callback is not None:
                progress_callback(
                    sampled_count,
                    total_samples,
                    saved_count,
                    event_count,
                )

            if sampled_count % progress_interval == 0:
                print(
                    f"已检查 {sampled_count} 个采样点，"
                    f"累计保存 {saved_count} 张截图。"
                )

        def process_pending_batch() -> None:
            if not pending_rois:
                return
            if cancel_check is not None and cancel_check():
                raise ProcessingCancelled("处理已取消。")

            observations = detect_text_observations(ocr, pending_rois)
            for roi_image, observation in zip(pending_rois, observations):
                signature, text_parts, line_length = observation
                apply_signature(
                    roi_image,
                    signature,
                    text_parts,
                    line_length,
                )
            pending_rois.clear()

        if progress_callback is not None:
            progress_callback(0, total_samples, 0, 0)

        while True:
            # grab() 推进视频帧；只在采样点使用 retrieve() 解码画面。
            if not capture.grab():
                break

            if frame_index % frame_step == 0:
                if cancel_check is not None and cancel_check():
                    raise ProcessingCancelled("处理已取消。")

                success, frame = capture.retrieve()
                if not success or frame is None:
                    raise ScriptError(f"读取视频帧失败，帧序号：{frame_index}")

                roi_bgr = frame[y1:y2, x1:x2]
                pending_rois.append(roi_bgr.copy())
                if len(pending_rois) >= OCR_BATCH_SIZE:
                    process_pending_batch()

            frame_index += 1

        process_pending_batch()
    finally:
        capture.release()

    return event_count, saved_count, sampled_count


def main(argv: Sequence[str] | None = None) -> int:
    """脚本主入口。"""
    args = parse_args(argv)
    validate_configuration()
    video_path = resolve_video_path(args.video)

    width, height, _fps, _frame_count = inspect_video(video_path)
    print(f"视频：{video_path}")
    print(f"分辨率：{width} x {height}")
    print("即将打开窗口，请用鼠标框选播报区域。")

    roi = select_roi_interactively(video_path)
    x1, y1, x2, y2 = roi

    output_root = video_path.parent / f"{video_path.stem}{OUTPUT_DIR_SUFFIX}"
    print(
        f"检测区域：({x1}, {y1}) 到 ({x2}, {y2})，"
        f"大小 {x2 - x1} x {y2 - y1}"
    )
    print(f"OCR 采样间隔：{OCR_INTERVAL_SECONDS:g} 秒")
    print(f"输出目录：{output_root}")
    print("正在加载 PaddleOCR；首次运行可能需要下载模型……")

    ocr = create_ocr()
    event_count, saved_count, sampled_count = process_video(
        video_path,
        output_root,
        ocr,
        roi,
    )

    print(
        f"处理完成：检查了 {sampled_count} 个采样点，"
        f"识别到 {event_count} 段播报，保存了 {saved_count} 张截图。"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\n已由用户中断。", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(
            f"运行失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)


# =============================================================================
# 安装命令（推荐使用 Python 3.11）：
#
# py -3.11 -m pip install --upgrade pip
# py -3.11 -m pip install paddlepaddle==3.3.1 paddleocr==3.7.0 opencv-contrib-python==4.10.0.84
#
# 重要提醒：
# 1. 如果换了布局不一样的录屏，建议重新运行脚本并重新框选播报区域。
# 2. OCR 置信度、文字框过滤尺寸等阈值可以自行修改。
# 3. 播报图文混杂，OCR 有可能识别失败，造成漏判或误判。
# =============================================================================
