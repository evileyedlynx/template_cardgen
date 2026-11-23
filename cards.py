#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Card Forge — Конструктор карточек для настольных игр
Python + PyQt6 версия
"""

import sys
import json
import math
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit,
    QComboBox, QCheckBox, QRadioButton, QPushButton, QColorDialog, QFileDialog,
    QScrollArea, QGroupBox, QFormLayout, QSplitter, QMessageBox,
    QListWidget, QListWidgetItem, QFrame, QSizePolicy, QMenu
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, QMarginsF, QByteArray
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontDatabase, QPixmap, QImage,
    QBrush, QPdfWriter, QPageSize, QPageLayout, QAction, QFontMetrics,
    QPainterPath, QTransform
)


# ============================================================
# МОДЕЛИ ДАННЫХ
# ============================================================

@dataclass
class BorderConfig:
    show: bool = True
    width: float = 2.0
    radius: float = 8.0
    color: str = "#1e293b"


@dataclass
class TextConfig:
    content: str = ""
    fontSize: float = 14.0
    color: str = "#0f172a"
    fontFamily: str = "Arial"
    position: str = "center"   # top / center / bottom (по Y)
    alignX: str = "center"     # left / center / right (по X)


@dataclass
class ChildFieldConfig:
    id: str = ""
    x: float = 0.5             # см от левого края родителя
    y: float = 0.5             # см от верхнего края родителя
    width: float = 4.0         # см
    height: float = 3.0        # см
    border: BorderConfig = field(default_factory=BorderConfig)
    text: TextConfig = field(default_factory=TextConfig)
    imageSrc: Optional[str] = None
    imgFit: bool = True
    imgCover: bool = False
    imgAlignX: str = "center"  # left / center / right
    imgAlignY: str = "center"  # top / center / bottom

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]


@dataclass
class FieldConfig:
    id: str = ""
    x: float = 0.5
    y: float = 0.5
    unit: str = "cm"
    width: float = 8.0
    height: float = 5.0
    border: BorderConfig = field(default_factory=BorderConfig)
    text: TextConfig = field(default_factory=TextConfig)
    imageSrc: Optional[str] = None
    imgFit: bool = True
    imgCover: bool = False
    imgAlignX: str = "center"  # left / center / right
    imgAlignY: str = "center"  # top / center / bottom
    children: List[ChildFieldConfig] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]


@dataclass
class ProjectConfig:
    version: int = 4
    cardWidthCm: float = 9.0
    cardHeightCm: float = 6.0
    cardBgColor: str = "#ffffff"
    fields: List[FieldConfig] = field(default_factory=list)


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

SCREEN_DPI = 96
CM_TO_PX = SCREEN_DPI / 2.54


def hex_to_qcolor(hex_str: str) -> QColor:
    return QColor(hex_str)


def load_system_fonts() -> List[str]:
    fonts = QFontDatabase.families()
    return sorted(fonts)


def draw_rounded_rect(painter: QPainter, rect: QRectF, radius: float):
    path = QPainterPath()
    r = min(radius, rect.width() / 2, rect.height() / 2)
    path.addRoundedRect(rect, r, r)
    return path


def wrap_text(painter: QPainter, text: str, max_width: float) -> List[str]:
    paragraphs = text.split('\n')
    lines = []
    fm = painter.fontMetrics()
    for para in paragraphs:
        if para == '':
            lines.append('')
            continue
        words = para.split(' ')
        line = ''
        for word in words:
            test_line = line + word + ' '
            if fm.horizontalAdvance(test_line) > max_width and line:
                lines.append(line.strip())
                line = word + ' '
            else:
                line = test_line
        lines.append(line.strip())
    return lines if lines else ['']


def fit_image(img_w: float, img_h: float, box_w: float, box_h: float, cover: bool):
    """Рассчитывает размеры изображения для fit/cover режима."""
    img_ratio = img_w / img_h
    box_ratio = box_w / box_h

    if cover:
        if img_ratio > box_ratio:
            draw_h = box_h
            draw_w = draw_h * img_ratio
        else:
            draw_w = box_w
            draw_h = draw_w / img_ratio
    else:
        if img_ratio > box_ratio:
            draw_w = box_w
            draw_h = draw_w / img_ratio
        else:
            draw_h = box_h
            draw_w = draw_h * img_ratio

    return draw_w, draw_h


def align_offset(available: float, used: float, align: str) -> float:
    """Возвращает смещение для выравнивания."""
    if align == "left" or align == "top":
        return 0.0
    elif align == "right" or align == "bottom":
        return available - used
    else:  # center
        return (available - used) / 2


# ============================================================
# ОТРИСОВКА КАРТЫ
# ============================================================

class CardRenderer:
    def __init__(self, project: ProjectConfig, images_cache: Dict[str, QImage]):
        self.project = project
        self.images_cache = images_cache

    def draw_card(self, painter: QPainter, x: float, y: float, w: float, h: float,
                  dpi: float, interactive: bool = False) -> Dict:
        scale_factor = dpi / SCREEN_DPI
        rects = {"fields": [], "children": []}

        painter.save()
        painter.fillRect(QRectF(x, y, w, h), hex_to_qcolor(self.project.cardBgColor))
        painter.restore()

        for i, field_cfg in enumerate(self.project.fields):
            if field_cfg.unit == "cm":
                fw = field_cfg.width * (dpi / 2.54)
                fh = field_cfg.height * (dpi / 2.54)
            else:
                fw = field_cfg.width * scale_factor
                fh = field_cfg.height * scale_factor

            fx = x + field_cfg.x * (dpi / 2.54)
            fy = y + field_cfg.y * (dpi / 2.54)

            self._draw_field(painter, fx, fy, fw, fh, field_cfg, dpi, scale_factor, i, interactive, rects)

            if interactive:
                rects["fields"].append({"x": fx, "y": fy, "w": fw, "h": fh, "idx": i})

        return rects

    def _draw_field(self, painter: QPainter, x: float, y: float, w: float, h: float,
                    cfg: FieldConfig, dpi: float, scale_factor: float, field_idx: int,
                    interactive: bool, rects: Dict):
        painter.save()

        r = cfg.border.radius * scale_factor
        rect = QRectF(x, y, w, h)
        path = draw_rounded_rect(painter, rect, r)

        painter.fillPath(path, QBrush(QColor("#ffffff")))

        if cfg.border.show:
            pen = QPen(hex_to_qcolor(cfg.border.color), cfg.border.width * scale_factor)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.save()
        painter.setClipPath(path)

        # Изображение родителя с учётом выравнивания
        if cfg.imageSrc and cfg.imageSrc in self.images_cache:
            self._draw_image(painter, x, y, w, h, cfg, dpi, scale_factor)

        # Текст родителя
        if cfg.text.content:
            self._draw_text(painter, x, y, w, h, cfg.text, dpi, scale_factor)

        # Дочерние поля
        if cfg.children:
            self._draw_children(painter, x, y, w, h, cfg, dpi, scale_factor, field_idx, interactive, rects)

        painter.restore()  # clip
        painter.restore()  # field

    def _draw_image(self, painter: QPainter, x: float, y: float, w: float, h: float,
                    cfg, dpi: float, scale_factor: float):
        """Рисует изображение с учётом fit/cover и выравнивания."""
        img = self.images_cache[cfg.imageSrc]
        pad = 3 * scale_factor
        box_x = x + pad
        box_y = y + pad
        box_w = w - pad * 2
        box_h = h - pad * 2

        draw_w, draw_h = fit_image(img.width(), img.height(), box_w, box_h, cfg.imgCover)

        # Выравнивание
        offset_x = align_offset(box_w, draw_w, cfg.imgAlignX)
        offset_y = align_offset(box_h, draw_h, cfg.imgAlignY)

        draw_x = box_x + offset_x
        draw_y = box_y + offset_y

        painter.drawImage(QRectF(draw_x, draw_y, draw_w, draw_h), img)

    def _draw_text(self, painter: QPainter, x: float, y: float, w: float, h: float,
                   text_cfg: TextConfig, dpi: float, scale_factor: float):
        font_size_px = text_cfg.fontSize * (dpi / 72)
        font = QFont(text_cfg.fontFamily)
        font.setPointSizeF(font_size_px * 72 / dpi)
        painter.setFont(font)
        painter.setPen(QPen(hex_to_qcolor(text_cfg.color)))

        max_width = w - 10 * scale_factor
        lines = wrap_text(painter, text_cfg.content, max_width)
        fm = painter.fontMetrics()
        line_height = fm.height() * 1.25
        total_text_height = len(lines) * line_height

        # Позиция по Y
        if text_cfg.position == "top":
            start_y = y + 10 * scale_factor
        elif text_cfg.position == "bottom":
            start_y = y + h - 10 * scale_factor - total_text_height
        else:
            start_y = y + (h / 2) - (total_text_height / 2)

        # Выравнивание по X
        if text_cfg.alignX == "left":
            align_flag = Qt.AlignmentFlag.AlignLeft
            text_rect = QRectF(x + 5 * scale_factor, start_y, w - 10 * scale_factor, total_text_height)
        elif text_cfg.alignX == "right":
            align_flag = Qt.AlignmentFlag.AlignRight
            text_rect = QRectF(x + 5 * scale_factor, start_y, w - 10 * scale_factor, total_text_height)
        else:
            align_flag = Qt.AlignmentFlag.AlignHCenter
            text_rect = QRectF(x, start_y, w, total_text_height)

        painter.drawText(text_rect, align_flag | Qt.AlignmentFlag.AlignTop, '\n'.join(lines))

    def _draw_children(self, painter: QPainter, field_x: float, field_y: float,
                       field_w: float, field_h: float, cfg: FieldConfig,
                       dpi: float, scale_factor: float, parent_idx: int,
                       interactive: bool, rects: Dict):
        px_per_cm = dpi / 2.54
        for ci, child in enumerate(cfg.children):
            # Абсолютные значения в см → пиксели
            child_x = field_x + child.x * px_per_cm
            child_y = field_y + child.y * px_per_cm
            child_w = child.width * px_per_cm
            child_h = child.height * px_per_cm

            self._draw_child_field(painter, child_x, child_y, child_w, child_h,
                                   child, dpi, scale_factor, parent_idx, ci, interactive)

            if interactive:
                rects["children"].append({
                    "x": child_x, "y": child_y, "w": child_w, "h": child_h,
                    "parentIdx": parent_idx, "childIdx": ci
                })

    def _draw_child_field(self, painter: QPainter, x: float, y: float, w: float, h: float,
                          cfg: ChildFieldConfig, dpi: float, scale_factor: float,
                          parent_idx: int, child_idx: int, interactive: bool):
        painter.save()

        r = cfg.border.radius * scale_factor
        rect = QRectF(x, y, w, h)
        path = draw_rounded_rect(painter, rect, r)

        painter.fillPath(path, QBrush(QColor("#ffffff")))

        if cfg.border.show:
            pen = QPen(hex_to_qcolor(cfg.border.color), cfg.border.width * scale_factor)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.save()
        painter.setClipPath(path)

        # Изображение с выравниванием
        if cfg.imageSrc and cfg.imageSrc in self.images_cache:
            self._draw_image(painter, x, y, w, h, cfg, dpi, scale_factor)

        # Текст
        if cfg.text.content:
            self._draw_text(painter, x, y, w, h, cfg.text, dpi, scale_factor)

        painter.restore()  # clip
        painter.restore()  # field


# ============================================================
# ВИДЖЕТ ПРЕВЬЮ
# ============================================================

class CardPreviewWidget(QWidget):
    def __init__(self, project: ProjectConfig, images_cache: Dict[str, QImage]):
        super().__init__()
        self.project = project
        self.images_cache = images_cache
        self.renderer = CardRenderer(project, images_cache)
        self.field_rects = {"fields": [], "children": []}
        self.selected_field_idx = 0
        self.selected_child_idx = -1
        self.setMinimumSize(400, 300)
        self.on_field_clicked = None
        self.on_child_clicked = None

    def update_preview(self):
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        card_w = self.project.cardWidthCm * CM_TO_PX
        card_h = self.project.cardHeightCm * CM_TO_PX

        offset_x = (self.width() - card_w) / 2
        offset_y = (self.height() - card_h) / 2

        self.field_rects = self.renderer.draw_card(
            painter, offset_x, offset_y, card_w, card_h, SCREEN_DPI, interactive=True
        )

        if self.field_rects["fields"] and self.selected_field_idx < len(self.field_rects["fields"]):
            sel = self.field_rects["fields"][self.selected_field_idx]
            painter.save()
            painter.setPen(QPen(QColor("#6366f1"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(sel["x"] - 2, sel["y"] - 2, sel["w"] + 4, sel["h"] + 4))
            painter.restore()

        if self.selected_child_idx >= 0:
            for cr in self.field_rects["children"]:
                if cr["parentIdx"] == self.selected_field_idx and cr["childIdx"] == self.selected_child_idx:
                    painter.save()
                    painter.setPen(QPen(QColor("#10b981"), 2, Qt.PenStyle.DashLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(QRectF(cr["x"] - 1, cr["y"] - 1, cr["w"] + 2, cr["h"] + 2))
                    painter.restore()
                    break

        painter.end()

    def mousePressEvent(self, event):
        mx = event.position().x()
        my = event.position().y()

        for cr in self.field_rects["children"]:
            if (cr["x"] <= mx <= cr["x"] + cr["w"] and
                    cr["y"] <= my <= cr["y"] + cr["h"]):
                if self.on_child_clicked:
                    self.on_child_clicked(cr["parentIdx"], cr["childIdx"])
                return

        for fr in self.field_rects["fields"]:
            if (fr["x"] <= mx <= fr["x"] + fr["w"] and
                    fr["y"] <= my <= fr["y"] + fr["h"]):
                if self.on_field_clicked:
                    self.on_field_clicked(fr["idx"])
                return


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ВИДЖЕТЫ
# ============================================================

class ColorButton(QPushButton):
    def __init__(self, initial_color: str = "#000000", parent=None):
        super().__init__(parent)
        self.color = initial_color
        self.setFixedSize(60, 30)
        self.update_style()
        self.clicked.connect(self.pick_color)

    def update_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color};
                border: 1px solid #cbd5e1;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border: 2px solid #6366f1;
            }}
        """)

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, "Выберите цвет")
        if color.isValid():
            self.color = color.name()
            self.update_style()

    def get_color(self) -> str:
        return self.color

    def set_color(self, color: str):
        self.color = color
        self.update_style()


class SectionGroup(QGroupBox):
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                color: #64748b;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
class FieldListItem(QWidget):
    """Кастомный виджет для строки списка полей с кнопкой удаления."""

    def __init__(self, text: str, on_delete, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        label = QLabel(text)
        label.setStyleSheet("color: #334155; font-size: 12px;")
        layout.addWidget(label)
        layout.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setToolTip("Удалить")
        del_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ef4444;
                border: none;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #fee2e2;
                border-radius: 4px;
            }
        """)
        del_btn.clicked.connect(on_delete)
        layout.addWidget(del_btn)

class FieldListItem(QWidget):
    """Кастомный виджет для строки списка полей с кнопкой удаления."""

    def __init__(self, text: str, on_delete, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        label = QLabel(text)
        label.setStyleSheet("color: #334155; font-size: 12px;")
        layout.addWidget(label)
        layout.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setToolTip("Удалить")
        del_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ef4444;
                border: none;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #fee2e2;
                border-radius: 4px;
            }
        """)
        del_btn.clicked.connect(on_delete)
        layout.addWidget(del_btn)

def make_spinbox(value: float, min_v: float, max_v: float, suffix: str = "",
                 decimals: int = 1, step: float = 0.1) -> QDoubleSpinBox:
    """Создаёт QDoubleSpinBox с инкрементом 0.1 по умолчанию."""
    sb = QDoubleSpinBox()
    sb.setRange(min_v, max_v)
    sb.setValue(value)
    sb.setDecimals(decimals)
    sb.setSingleStep(step)
    if suffix:
        sb.setSuffix(suffix)
    return sb


# ============================================================
# ГЛАВНОЕ ОКНО
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Card Forge — Конструктор карточек")
        self.resize(1400, 900)

        self.project = ProjectConfig(fields=[FieldConfig()])
        self.images_cache: Dict[str, QImage] = {}
        self.selected_field_idx = 0
        self.selected_child_idx = -1

        self._setup_ui()
        self._connect_signals()
        self._sync_ui_from_state()
        self._update_info()
        self.preview_widget.update_preview()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Левая панель
        left_panel = QWidget()
        left_panel.setFixedWidth(420)
        left_panel.setStyleSheet("background-color: white;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #6366f1, stop:1 #9333ea);
            padding: 16px;
        """)
        header_layout = QVBoxLayout(header)
        title = QLabel("Card Forge")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        subtitle = QLabel("Конструктор карточек для настольных игр")
        subtitle.setStyleSheet("color: #e0e7ff; font-size: 11px;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        header_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                padding: 8px 16px;
                font-size: 12px;
                background: #f1f5f9;
                border: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #6366f1;
                color: white;
            }
        """)

        self.tab_card = self._create_card_tab()
        self.tabs.addTab(self.tab_card, "Карта")
        self.tab_fields = self._create_fields_tab()
        self.tabs.addTab(self.tab_fields, "Поля")
        self.tab_export = self._create_export_tab()
        self.tabs.addTab(self.tab_export, "Экспорт")

        left_layout.addWidget(self.tabs)

        # Правая панель
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #f1f5f9;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        info_bar = QWidget()
        info_bar.setStyleSheet("background: white; border-bottom: 1px solid #e2e8f0;")
        info_layout = QHBoxLayout(info_bar)
        self.info_label = QLabel("Превью карты · 9 × 6 см")
        self.info_label.setStyleSheet("color: #475569; font-size: 13px;")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        right_layout.addWidget(info_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #f1f5f9; }")

        self.preview_widget = CardPreviewWidget(self.project, self.images_cache)
        self.preview_widget.setMinimumSize(800, 600)
        self.preview_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_widget.on_field_clicked = self._on_field_clicked
        self.preview_widget.on_child_clicked = self._on_child_clicked

        scroll.setWidget(self.preview_widget)
        right_layout.addWidget(scroll)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _create_card_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        size_group = SectionGroup("Размер карты")
        size_layout = QFormLayout(size_group)
        self.card_width = make_spinbox(9.0, 1, 100, " см")
        self.card_height = make_spinbox(6.0, 1, 100, " см")
        size_layout.addRow("Ширина:", self.card_width)
        size_layout.addRow("Высота:", self.card_height)
        layout.addWidget(size_group)

        bg_group = SectionGroup("Фон карты")
        bg_layout = QHBoxLayout(bg_group)
        self.card_bg_color = ColorButton("#ffffff")
        self.card_bg_hex = QLabel("#ffffff")
        self.card_bg_hex.setStyleSheet("color: #64748b; font-size: 11px;")
        bg_layout.addWidget(self.card_bg_color)
        bg_layout.addWidget(self.card_bg_hex)
        bg_layout.addStretch()
        layout.addWidget(bg_group)

        info_group = SectionGroup("Информация")
        info_layout = QVBoxLayout(info_group)
        self.info_card_size = QLabel("Размер карты: 9 × 6 см")
        self.info_field_count = QLabel("Кол-во полей: 1")
        self.info_selected_field = QLabel("Выбрано поле: #1")
        for lbl in [self.info_card_size, self.info_field_count, self.info_selected_field]:
            lbl.setStyleSheet("color: #475569; font-size: 12px;")
            info_layout.addWidget(lbl)
        layout.addWidget(info_group)

        layout.addStretch()
        return widget

    def _create_fields_tab(self) -> QWidget:
        widget = QWidget()
        outer_layout = QVBoxLayout(widget)
        outer_layout.setContentsMargins(16, 16, 16, 16)
        outer_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Заголовок списка полей
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Список полей</b>"))
        header.addStretch()
        self.add_field_btn = QPushButton("+ Добавить")
        self.add_field_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #6366f1; border: none;
                font-weight: bold; font-size: 12px; }
            QPushButton:hover { color: #4f46e5; }
        """)
        header.addWidget(self.add_field_btn)
        layout.addLayout(header)

        self.field_list = QListWidget()
        self.field_list.setMaximumHeight(140)
        self.field_list.setStyleSheet("""
            QListWidget { border: 1px solid #e2e8f0; border-radius: 6px; background: #f8fafc; }
            QListWidget::item { padding: 6px; border-radius: 4px; }
            QListWidget::item:selected { background: #eef2ff; color: #6366f1; }
            QListWidget::item:hover { background: #f1f5f9; }
        """)
        layout.addWidget(self.field_list)

        # === Настройки поля ===
        pos_group = SectionGroup("Позиция поля на карте")
        pos_layout = QFormLayout(pos_group)
        self.field_x = make_spinbox(0.5, 0, 100, " см")
        self.field_y = make_spinbox(0.5, 0, 100, " см")
        pos_layout.addRow("X (от левого края):", self.field_x)
        pos_layout.addRow("Y (от верхнего края):", self.field_y)
        layout.addWidget(pos_group)

        size_group = SectionGroup("Размер поля")
        size_layout = QVBoxLayout(size_group)
        unit_layout = QHBoxLayout()
        self.unit_cm = QRadioButton("см")
        self.unit_px = QRadioButton("пикс. (96 DPI)")
        self.unit_cm.setChecked(True)
        unit_layout.addWidget(self.unit_cm)
        unit_layout.addWidget(self.unit_px)
        unit_layout.addStretch()
        size_layout.addLayout(unit_layout)

        dims_layout = QFormLayout()
        self.field_width = make_spinbox(8.0, 0.1, 1000)
        self.field_height = make_spinbox(5.0, 0.1, 1000)
        dims_layout.addRow("Ширина:", self.field_width)
        dims_layout.addRow("Высота:", self.field_height)
        size_layout.addLayout(dims_layout)
        layout.addWidget(size_group)

        # Рамка
        border_group = SectionGroup("Рамка")
        border_layout = QFormLayout(border_group)
        self.show_border = QCheckBox("Показывать рамку")
        self.show_border.setChecked(True)
        border_layout.addRow(self.show_border)
        self.border_width = make_spinbox(2.0, 0, 50, " px", step=1.0)
        self.border_radius = make_spinbox(8.0, 0, 100, " px", step=1.0)
        border_layout.addRow("Толщина:", self.border_width)
        border_layout.addRow("Скругление:", self.border_radius)
        color_row = QHBoxLayout()
        self.border_color = ColorButton("#1e293b")
        color_row.addWidget(self.border_color)
        color_row.addStretch()
        border_layout.addRow("Цвет:", color_row)
        layout.addWidget(border_group)

        # Текст
        text_group = SectionGroup("Текст")
        text_layout = QFormLayout(text_group)
        self.field_text = QTextEdit()
        self.field_text.setMaximumHeight(60)
        self.field_text.setPlaceholderText("Текст надписи...")
        text_layout.addRow("Содержимое:", self.field_text)

        self.font_size = make_spinbox(14.0, 1, 200, " pt")
        text_layout.addRow("Размер:", self.font_size)

        color_row2 = QHBoxLayout()
        self.text_color = ColorButton("#0f172a")
        color_row2.addWidget(self.text_color)
        color_row2.addStretch()
        text_layout.addRow("Цвет текста:", color_row2)

        self.font_family = QComboBox()
        self.font_family.addItems(load_system_fonts())
        self.font_family.setEditable(True)
        text_layout.addRow("Шрифт:", self.font_family)

        self.text_position = QComboBox()
        self.text_position.addItems(["center", "top", "bottom"])
        self.text_position.setItemText(0, "По центру (Y)")
        self.text_position.setItemText(1, "Сверху")
        self.text_position.setItemText(2, "Снизу")
        text_layout.addRow("Позиция (Y):", self.text_position)

        # НОВОЕ: выравнивание по X
        self.text_align_x = QComboBox()
        self.text_align_x.addItems(["left", "center", "right"])
        self.text_align_x.setItemText(0, "Слева")
        self.text_align_x.setItemText(1, "По центру")
        self.text_align_x.setItemText(2, "Справа")
        text_layout.addRow("Выравнивание (X):", self.text_align_x)

        layout.addWidget(text_group)

        # Изображение
        img_group = SectionGroup("Изображение")
        img_layout = QVBoxLayout(img_group)
        self.load_img_btn = QPushButton("📁 Загрузить изображение")
        self.load_img_btn.setStyleSheet("""
            QPushButton { background: #f8fafc; border: 2px dashed #cbd5e1;
                border-radius: 6px; padding: 12px; color: #64748b; }
            QPushButton:hover { background: #f1f5f9; border-color: #6366f1; }
        """)
        img_layout.addWidget(self.load_img_btn)

        fit_layout = QHBoxLayout()
        self.img_fit = QCheckBox("Подгонять размер")
        self.img_fit.setChecked(True)
        self.img_cover = QCheckBox("Режим Cover")
        fit_layout.addWidget(self.img_fit)
        fit_layout.addWidget(self.img_cover)
        fit_layout.addStretch()
        img_layout.addLayout(fit_layout)

        # НОВОЕ: выравнивание изображения
        img_align_layout = QFormLayout()
        self.img_align_x = QComboBox()
        self.img_align_x.addItems(["left", "center", "right"])
        self.img_align_x.setItemText(0, "Слева")
        self.img_align_x.setItemText(1, "По центру")
        self.img_align_x.setItemText(2, "Справа")
        img_align_layout.addRow("Выравнивание (X):", self.img_align_x)

        self.img_align_y = QComboBox()
        self.img_align_y.addItems(["top", "center", "bottom"])
        self.img_align_y.setItemText(0, "Сверху")
        self.img_align_y.setItemText(1, "По центру")
        self.img_align_y.setItemText(2, "Снизу")
        img_align_layout.addRow("Выравнивание (Y):", self.img_align_y)
        img_layout.addLayout(img_align_layout)

        self.remove_img_btn = QPushButton("❌ Удалить изображение")
        self.remove_img_btn.setStyleSheet("color: #ef4444;")
        self.remove_img_btn.setVisible(False)
        img_layout.addWidget(self.remove_img_btn)
        layout.addWidget(img_group)

        # === Дочерние поля ===
        child_header = QHBoxLayout()
        child_header.addWidget(QLabel("<b>Дочерние поля</b>"))
        child_header.addStretch()
        self.add_child_btn = QPushButton("+ Добавить")
        self.add_child_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #10b981; border: none;
                font-weight: bold; font-size: 12px; }
            QPushButton:hover { color: #059669; }
        """)
        child_header.addWidget(self.add_child_btn)
        layout.addLayout(child_header)

        info_lbl = QLabel("💡 Каждое дочернее поле размещается произвольно внутри родительского. Координаты и размер — в сантиметрах.")
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("background: #ecfdf5; color: #065f46; padding: 8px; border-radius: 6px; font-size: 11px;")
        layout.addWidget(info_lbl)

        self.child_list = QListWidget()
        self.child_list.setMaximumHeight(120)
        self.child_list.setStyleSheet("""
            QListWidget { border: 1px solid #d1fae5; border-radius: 6px; background: #f0fdf4; }
            QListWidget::item:selected { background: #dcfce7; color: #10b981; }
        """)
        layout.addWidget(self.child_list)

        # Настройки дочернего поля
        self.child_editor = QWidget()
        child_layout = QVBoxLayout(self.child_editor)
        child_layout.setContentsMargins(0, 0, 0, 0)

        child_pos_group = SectionGroup("Позиция и размер дочернего поля (см)")
        child_pos_layout = QFormLayout(child_pos_group)
        self.child_x = make_spinbox(0.5, 0, 100, " см")
        self.child_y = make_spinbox(0.5, 0, 100, " см")
        self.child_width = make_spinbox(4.0, 0.1, 100, " см")
        self.child_height = make_spinbox(3.0, 0.1, 100, " см")
        child_pos_layout.addRow("X (от левого края):", self.child_x)
        child_pos_layout.addRow("Y (от верхнего края):", self.child_y)
        child_pos_layout.addRow("Ширина:", self.child_width)
        child_pos_layout.addRow("Высота:", self.child_height)
        child_layout.addWidget(child_pos_group)

        # Рамка дочернего
        child_border_group = SectionGroup("Рамка дочернего поля")
        child_border_layout = QFormLayout(child_border_group)
        self.child_show_border = QCheckBox("Показывать рамку")
        self.child_show_border.setChecked(True)
        child_border_layout.addRow(self.child_show_border)
        self.child_border_width = make_spinbox(1.0, 0, 50, " px", step=1.0)
        self.child_border_radius = make_spinbox(4.0, 0, 100, " px", step=1.0)
        child_border_layout.addRow("Толщина:", self.child_border_width)
        child_border_layout.addRow("Скругление:", self.child_border_radius)
        child_color_row = QHBoxLayout()
        self.child_border_color = ColorButton("#059669")
        child_color_row.addWidget(self.child_border_color)
        child_color_row.addStretch()
        child_border_layout.addRow("Цвет:", child_color_row)
        child_layout.addWidget(child_border_group)

        # Текст дочернего
        child_text_group = SectionGroup("Текст дочернего поля")
        child_text_layout = QFormLayout(child_text_group)
        self.child_text = QTextEdit()
        self.child_text.setMaximumHeight(60)
        self.child_text.setPlaceholderText("Текст...")
        child_text_layout.addRow("Содержимое:", self.child_text)
        self.child_font_size = make_spinbox(10.0, 1, 200, " pt")
        child_text_layout.addRow("Размер:", self.child_font_size)
        child_color_row2 = QHBoxLayout()
        self.child_text_color = ColorButton("#0f172a")
        child_color_row2.addWidget(self.child_text_color)
        child_color_row2.addStretch()
        child_text_layout.addRow("Цвет текста:", child_color_row2)
        self.child_font_family = QComboBox()
        self.child_font_family.addItems(load_system_fonts())
        self.child_font_family.setEditable(True)
        child_text_layout.addRow("Шрифт:", self.child_font_family)
        self.child_text_position = QComboBox()
        self.child_text_position.addItems(["center", "top", "bottom"])
        self.child_text_position.setItemText(0, "По центру (Y)")
        self.child_text_position.setItemText(1, "Сверху")
        self.child_text_position.setItemText(2, "Снизу")
        child_text_layout.addRow("Позиция (Y):", self.child_text_position)
        self.child_text_align_x = QComboBox()
        self.child_text_align_x.addItems(["left", "center", "right"])
        self.child_text_align_x.setItemText(0, "Слева")
        self.child_text_align_x.setItemText(1, "По центру")
        self.child_text_align_x.setItemText(2, "Справа")
        child_text_layout.addRow("Выравнивание (X):", self.child_text_align_x)
        child_layout.addWidget(child_text_group)

        # Изображение дочернего
        child_img_group = SectionGroup("Изображение дочернего поля")
        child_img_layout = QVBoxLayout(child_img_group)
        self.load_child_img_btn = QPushButton("📁 Загрузить изображение")
        self.load_child_img_btn.setStyleSheet("""
            QPushButton { background: #f8fafc; border: 2px dashed #cbd5e1;
                border-radius: 6px; padding: 12px; color: #64748b; }
            QPushButton:hover { background: #f1f5f9; border-color: #10b981; }
        """)
        child_img_layout.addWidget(self.load_child_img_btn)

        child_fit_layout = QHBoxLayout()
        self.child_img_fit = QCheckBox("Подгонять размер")
        self.child_img_fit.setChecked(True)
        self.child_img_cover = QCheckBox("Режим Cover")
        child_fit_layout.addWidget(self.child_img_fit)
        child_fit_layout.addWidget(self.child_img_cover)
        child_fit_layout.addStretch()
        child_img_layout.addLayout(child_fit_layout)

        # Выравнивание изображения дочернего
        child_img_align_layout = QFormLayout()
        self.child_img_align_x = QComboBox()
        self.child_img_align_x.addItems(["left", "center", "right"])
        self.child_img_align_x.setItemText(0, "Слева")
        self.child_img_align_x.setItemText(1, "По центру")
        self.child_img_align_x.setItemText(2, "Справа")
        child_img_align_layout.addRow("Выравнивание (X):", self.child_img_align_x)

        self.child_img_align_y = QComboBox()
        self.child_img_align_y.addItems(["top", "center", "bottom"])
        self.child_img_align_y.setItemText(0, "Сверху")
        self.child_img_align_y.setItemText(1, "По центру")
        self.child_img_align_y.setItemText(2, "Снизу")
        child_img_align_layout.addRow("Выравнивание (Y):", self.child_img_align_y)
        child_img_layout.addLayout(child_img_align_layout)

        self.remove_child_img_btn = QPushButton("❌ Удалить изображение")
        self.remove_child_img_btn.setStyleSheet("color: #ef4444;")
        self.remove_child_img_btn.setVisible(False)
        child_img_layout.addWidget(self.remove_child_img_btn)
        child_layout.addWidget(child_img_group)

        self.child_editor.setVisible(False)
        layout.addWidget(self.child_editor)

        layout.addStretch()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        return widget

    def _create_export_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        save_group = SectionGroup("Сохранение проекта")
        save_layout = QHBoxLayout(save_group)
        self.save_json_btn = QPushButton("💾 Сохранить JSON")
        self.save_json_btn.setStyleSheet("""
            QPushButton { background: white; border: 1px solid #e2e8f0;
                border-radius: 6px; padding: 8px 14px; font-weight: 500; }
            QPushButton:hover { background: #f8fafc; }
        """)
        self.load_json_btn = QPushButton("📂 Загрузить JSON")
        self.load_json_btn.setStyleSheet("""
            QPushButton { background: white; border: 1px solid #e2e8f0;
                border-radius: 6px; padding: 8px 14px; font-weight: 500; }
            QPushButton:hover { background: #f8fafc; }
        """)
        save_layout.addWidget(self.save_json_btn)
        save_layout.addWidget(self.load_json_btn)
        layout.addWidget(save_group)

        png_group = SectionGroup("Экспорт одной карты")
        png_layout = QFormLayout(png_group)
        self.export_dpi = QComboBox()
        self.export_dpi.addItems(["96 DPI (экран)", "150 DPI", "300 DPI (печать)", "600 DPI"])
        self.export_dpi.setCurrentIndex(2)
        png_layout.addRow("Масштаб:", self.export_dpi)
        self.export_png_btn = QPushButton("🖼 Скачать PNG карты")
        self.export_png_btn.setStyleSheet("""
            QPushButton { background: #6366f1; color: white; border: none;
                border-radius: 6px; padding: 10px; font-weight: 500; }
            QPushButton:hover { background: #4f46e5; }
        """)
        png_layout.addRow(self.export_png_btn)
        layout.addWidget(png_group)

        print_group = SectionGroup("Печать на A4")
        print_layout = QFormLayout(print_group)
        self.print_copies = QSpinBox()
        self.print_copies.setRange(1, 1000)
        self.print_copies.setValue(1)
        print_layout.addRow("Копий карты:", self.print_copies)
        self.print_dpi = QComboBox()
        self.print_dpi.addItems(["150 DPI", "300 DPI", "600 DPI"])
        self.print_dpi.setCurrentIndex(1)
        print_layout.addRow("Качество:", self.print_dpi)
        self.print_cut_lines = QCheckBox("Добавить линии отреза")
        print_layout.addRow(self.print_cut_lines)
        self.print_sheet_btn = QPushButton("🖨 Сформировать лист A4")
        self.print_sheet_btn.setStyleSheet("""
            QPushButton { background: #10b981; color: white; border: none;
                border-radius: 6px; padding: 10px; font-weight: 500; }
            QPushButton:hover { background: #059669; }
        """)
        print_layout.addRow(self.print_sheet_btn)
        layout.addWidget(print_group)

        hint = QLabel("💡 Для массовой печати: сохраните несколько JSON-проектов, затем загружайте их по очереди и формируйте листы A4.")
        hint.setWordWrap(True)
        hint.setStyleSheet("background: #eef2ff; color: #3730a3; padding: 10px; border-radius: 6px; font-size: 11px;")
        layout.addWidget(hint)

        layout.addStretch()
        return widget

    def _connect_signals(self):
        # Карта
        self.card_width.valueChanged.connect(self._on_card_size_changed)
        self.card_height.valueChanged.connect(self._on_card_size_changed)
        self.card_bg_color.clicked.connect(self._on_card_bg_changed)

        # Поля
        self.add_field_btn.clicked.connect(self._on_add_field)
        self.field_list.currentRowChanged.connect(self._on_field_selected)

        self.field_x.valueChanged.connect(self._on_field_changed)
        self.field_y.valueChanged.connect(self._on_field_changed)
        self.field_width.valueChanged.connect(self._on_field_changed)
        self.field_height.valueChanged.connect(self._on_field_changed)
        self.unit_cm.toggled.connect(self._on_field_changed)
        self.show_border.toggled.connect(self._on_field_changed)
        self.border_width.valueChanged.connect(self._on_field_changed)
        self.border_radius.valueChanged.connect(self._on_field_changed)
        self.border_color.clicked.connect(self._on_field_changed)
        self.field_text.textChanged.connect(self._on_field_changed)
        self.font_size.valueChanged.connect(self._on_field_changed)
        self.text_color.clicked.connect(self._on_field_changed)
        self.font_family.currentTextChanged.connect(self._on_field_changed)
        self.text_position.currentIndexChanged.connect(self._on_field_changed)
        self.text_align_x.currentIndexChanged.connect(self._on_field_changed)

        self.load_img_btn.clicked.connect(self._on_load_image)
        self.remove_img_btn.clicked.connect(self._on_remove_image)
        self.img_fit.toggled.connect(self._on_field_changed)
        self.img_cover.toggled.connect(self._on_field_changed)
        self.img_align_x.currentIndexChanged.connect(self._on_field_changed)
        self.img_align_y.currentIndexChanged.connect(self._on_field_changed)

        # Дочерние поля
        self.add_child_btn.clicked.connect(self._on_add_child)
        self.child_list.currentRowChanged.connect(self._on_child_selected)

        self.child_x.valueChanged.connect(self._on_child_changed)
        self.child_y.valueChanged.connect(self._on_child_changed)
        self.child_width.valueChanged.connect(self._on_child_changed)
        self.child_height.valueChanged.connect(self._on_child_changed)
        self.child_show_border.toggled.connect(self._on_child_changed)
        self.child_border_width.valueChanged.connect(self._on_child_changed)
        self.child_border_radius.valueChanged.connect(self._on_child_changed)
        self.child_border_color.clicked.connect(self._on_child_changed)
        self.child_text.textChanged.connect(self._on_child_changed)
        self.child_font_size.valueChanged.connect(self._on_child_changed)
        self.child_text_color.clicked.connect(self._on_child_changed)
        self.child_font_family.currentTextChanged.connect(self._on_child_changed)
        self.child_text_position.currentIndexChanged.connect(self._on_child_changed)
        self.child_text_align_x.currentIndexChanged.connect(self._on_child_changed)

        self.load_child_img_btn.clicked.connect(self._on_load_child_image)
        self.remove_child_img_btn.clicked.connect(self._on_remove_child_image)
        self.child_img_fit.toggled.connect(self._on_child_changed)
        self.child_img_cover.toggled.connect(self._on_child_changed)
        self.child_img_align_x.currentIndexChanged.connect(self._on_child_changed)
        self.child_img_align_y.currentIndexChanged.connect(self._on_child_changed)

        # Экспорт
        self.save_json_btn.clicked.connect(self._on_save_json)
        self.load_json_btn.clicked.connect(self._on_load_json)
        self.export_png_btn.clicked.connect(self._on_export_png)
        self.print_sheet_btn.clicked.connect(self._on_print_sheet)

    # ============================================================
    # ОБРАБОТЧИКИ — КАРТА
    # ============================================================

    def _on_card_size_changed(self):
        self.project.cardWidthCm = self.card_width.value()
        self.project.cardHeightCm = self.card_height.value()
        self._update_info()
        self.preview_widget.update_preview()

    def _on_card_bg_changed(self):
        self.project.cardBgColor = self.card_bg_color.get_color()
        self.card_bg_hex.setText(self.project.cardBgColor)
        self.preview_widget.update_preview()

    # ============================================================
    # ОБРАБОТЧИКИ — ПОЛЯ
    # ============================================================

    def _current_field(self) -> Optional[FieldConfig]:
        if 0 <= self.selected_field_idx < len(self.project.fields):
            return self.project.fields[self.selected_field_idx]
        return None

    def _current_child(self) -> Optional[ChildFieldConfig]:
        f = self._current_field()
        if f and 0 <= self.selected_child_idx < len(f.children):
            return f.children[self.selected_child_idx]
        return None

    def _on_add_field(self):
        self.project.fields.append(FieldConfig())
        self.selected_field_idx = len(self.project.fields) - 1
        self.selected_child_idx = -1
        self._rebuild_field_list()
        self._sync_ui_from_state()
        self._update_info()
        self.preview_widget.update_preview()

    def _on_delete_field(self, idx: int):
        if len(self.project.fields) <= 1:
            QMessageBox.warning(self, "Нельзя удалить", "Должно остаться хотя бы одно поле")
            return
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить поле #{idx + 1}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.project.fields.pop(idx)
        if self.selected_field_idx >= len(self.project.fields):
            self.selected_field_idx = len(self.project.fields) - 1
        self.selected_child_idx = -1
        self._rebuild_field_list()
        self._sync_ui_from_state()
        self._update_info()
        self.preview_widget.update_preview()

    def _on_field_selected(self, row: int):
        if row >= 0:
            self.selected_field_idx = row
            self.selected_child_idx = -1
            self._sync_ui_from_state()
            self._update_info()
            self.preview_widget.update_preview()

    def _on_field_changed(self):
        f = self._current_field()
        if not f:
            return
        f.x = self.field_x.value()
        f.y = self.field_y.value()
        f.width = self.field_width.value()
        f.height = self.field_height.value()
        f.unit = "cm" if self.unit_cm.isChecked() else "px"
        f.border.show = self.show_border.isChecked()
        f.border.width = self.border_width.value()
        f.border.radius = self.border_radius.value()
        f.border.color = self.border_color.get_color()
        f.text.content = self.field_text.toPlainText()
        f.text.fontSize = self.font_size.value()
        f.text.color = self.text_color.get_color()
        f.text.fontFamily = self.font_family.currentText()
        f.text.position = ["center", "top", "bottom"][self.text_position.currentIndex()]
        f.text.alignX = ["left", "center", "right"][self.text_align_x.currentIndex()]
        f.imgFit = self.img_fit.isChecked()
        f.imgCover = self.img_cover.isChecked()
        f.imgAlignX = ["left", "center", "right"][self.img_align_x.currentIndex()]
        f.imgAlignY = ["top", "center", "bottom"][self.img_align_y.currentIndex()]

        if 0 <= self.selected_field_idx < self.field_list.count():
            item = self.field_list.item(self.selected_field_idx)
            size_label = f"{f.width}{f.unit} × {f.height}{f.unit}"
            child_count = len(f.children)
            child_info = f" +{child_count} доч." if child_count > 0 else ""
            item.setText(f"#{self.selected_field_idx + 1}  {size_label}{child_info}")

        self.preview_widget.update_preview()

    def _on_load_image(self):
        f = self._current_field()
        if not f:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение")
            return
        img_id = str(uuid.uuid4())[:12]
        self.images_cache[img_id] = img
        f.imageSrc = img_id
        self.remove_img_btn.setVisible(True)
        self.preview_widget.update_preview()

    def _on_remove_image(self):
        f = self._current_field()
        if f:
            f.imageSrc = None
        self.remove_img_btn.setVisible(False)
        self.preview_widget.update_preview()

    # ============================================================
    # ОБРАБОТЧИКИ — ДОЧЕРНИЕ ПОЛЯ
    # ============================================================

    def _on_add_child(self):
        f = self._current_field()
        if not f:
            return
        f.children.append(ChildFieldConfig())
        self.selected_child_idx = len(f.children) - 1
        self._rebuild_child_list()
        self._sync_ui_from_state()
        self.preview_widget.update_preview()

    def _on_delete_child(self, idx: int):
        f = self._current_field()
        if not f:
            return
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить дочернее поле #{idx + 1}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        f.children.pop(idx)
        if self.selected_child_idx >= len(f.children):
            self.selected_child_idx = len(f.children) - 1 if f.children else -1
        self._rebuild_child_list()
        self._sync_ui_from_state()
        self.preview_widget.update_preview()

    def _on_child_selected(self, row: int):
        if row >= 0:
            self.selected_child_idx = row
            self._sync_ui_from_state()
            self.preview_widget.update_preview()

    def _on_child_changed(self):
        cf = self._current_child()
        if not cf:
            return
        cf.x = self.child_x.value()
        cf.y = self.child_y.value()
        cf.width = self.child_width.value()
        cf.height = self.child_height.value()
        cf.border.show = self.child_show_border.isChecked()
        cf.border.width = self.child_border_width.value()
        cf.border.radius = self.child_border_radius.value()
        cf.border.color = self.child_border_color.get_color()
        cf.text.content = self.child_text.toPlainText()
        cf.text.fontSize = self.child_font_size.value()
        cf.text.color = self.child_text_color.get_color()
        cf.text.fontFamily = self.child_font_family.currentText()
        cf.text.position = ["center", "top", "bottom"][self.child_text_position.currentIndex()]
        cf.text.alignX = ["left", "center", "right"][self.child_text_align_x.currentIndex()]
        cf.imgFit = self.child_img_fit.isChecked()
        cf.imgCover = self.child_img_cover.isChecked()
        cf.imgAlignX = ["left", "center", "right"][self.child_img_align_x.currentIndex()]
        cf.imgAlignY = ["top", "center", "bottom"][self.child_img_align_y.currentIndex()]

        if 0 <= self.selected_child_idx < self.child_list.count():
            item = self.child_list.item(self.selected_child_idx)
            item.setText(
                f"⊞ {self.selected_child_idx + 1}  {cf.width}×{cf.height}см @ ({cf.x},{cf.y})")

        self.preview_widget.update_preview()

    def _on_load_child_image(self):
        cf = self._current_child()
        if not cf:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение")
            return
        img_id = str(uuid.uuid4())[:12]
        self.images_cache[img_id] = img
        cf.imageSrc = img_id
        self.remove_child_img_btn.setVisible(True)
        self.preview_widget.update_preview()

    def _on_remove_child_image(self):
        cf = self._current_child()
        if cf:
            cf.imageSrc = None
        self.remove_child_img_btn.setVisible(False)
        self.preview_widget.update_preview()

    # ============================================================
    # ОБРАБОТЧИКИ — ЭКСПОРТ
    # ============================================================

    def _get_export_dpi(self) -> float:
        return [96, 150, 300, 600][self.export_dpi.currentIndex()]

    def _get_print_dpi(self) -> float:
        return [150, 300, 600][self.print_dpi.currentIndex()]

    def _on_save_json(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить проект", f"card_project_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON файлы (*.json)"
        )
        if not path:
            return
        try:
            data = self._project_to_dict()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Успех", "Проект сохранён")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")

    def _on_load_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить проект", "",
            "JSON файлы (*.json)"
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._dict_to_project(data)
            self.selected_field_idx = 0
            self.selected_child_idx = -1
            self._rebuild_field_list()
            self._rebuild_child_list()
            self._sync_ui_from_state()
            self._update_info()
            self.preview_widget.update_preview()
            QMessageBox.information(self, "Успех", "Проект загружен")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить: {e}")

    def _on_export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить PNG", f"card_{self.project.cardWidthCm}x{self.project.cardHeightCm}cm.png",
            "PNG файлы (*.png)"
        )
        if not path:
            return
        try:
            dpi = self._get_export_dpi()
            w = int(self.project.cardWidthCm * 10 * dpi / 25.4)
            h = int(self.project.cardHeightCm * 10 * dpi / 25.4)
            image = QImage(w, h, QImage.Format.Format_ARGB32)
            image.fill(QColor("#ffffff"))

            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

            renderer = CardRenderer(self.project, self.images_cache)
            renderer.draw_card(painter, 0, 0, w, h, dpi, interactive=False)
            painter.end()

            if image.save(path, "PNG"):
                QMessageBox.information(self, "Успех", f"Изображение сохранено:\n{path}")
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось сохранить изображение")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать: {e}")

    def _on_print_sheet(self):
        try:
            dpi = self._get_print_dpi()
            copies = self.print_copies.value()
            cut_lines = self.print_cut_lines.isChecked()

            a4_w_mm, a4_h_mm = 210, 297
            px_per_mm = dpi / 25.4
            page_w = int(a4_w_mm * px_per_mm)
            page_h = int(a4_h_mm * px_per_mm)

            card_w = self.project.cardWidthCm * 10 * px_per_mm
            card_h = self.project.cardHeightCm * 10 * px_per_mm

            margin = 5 * px_per_mm
            avail_w = page_w - margin * 2
            avail_h = page_h - margin * 2

            cols_on_page = max(1, int(avail_w / card_w))
            rows_on_page = max(1, int(avail_h / card_h))
            per_page = cols_on_page * rows_on_page
            pages_needed = math.ceil(copies / per_page)

            temp_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения страниц")
            if not temp_dir:
                return

            renderer = CardRenderer(self.project, self.images_cache)

            for p in range(pages_needed):
                image = QImage(page_w, page_h, QImage.Format.Format_ARGB32)
                image.fill(QColor("#ffffff"))
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

                block_w = cols_on_page * card_w
                block_h = rows_on_page * card_h
                start_x = (page_w - block_w) / 2
                start_y = (page_h - block_h) / 2

                drawn = 0
                remaining = copies - p * per_page
                for r in range(rows_on_page):
                    if drawn >= remaining:
                        break
                    for c in range(cols_on_page):
                        if drawn >= remaining:
                            break
                        x = start_x + c * card_w
                        y = start_y + r * card_h
                        renderer.draw_card(painter, x, y, card_w, card_h, dpi, interactive=False)
                        if cut_lines:
                            pen = QPen(QColor("#94a3b8"), 1, Qt.PenStyle.DashLine)
                            painter.setPen(pen)
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.drawRect(QRectF(x, y, card_w, card_h))
                        drawn += 1

                painter.end()
                image.save(f"{temp_dir}/page_{p + 1}.png", "PNG")

            QMessageBox.information(
                self, "Успех",
                f"Сформировано {pages_needed} страниц(а).\nФайлы сохранены в:\n{temp_dir}\n\n"
                f"Откройте файлы и распечатайте."
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сформировать лист: {e}")

    # ============================================================
    # КЛИК ПО ПРЕВЬЮ
    # ============================================================

    def _on_field_clicked(self, idx: int):
        self.selected_field_idx = idx
        self.selected_child_idx = -1
        self.field_list.setCurrentRow(idx)
        self.tabs.setCurrentIndex(1)
        self._sync_ui_from_state()
        self._update_info()
        self.preview_widget.update_preview()

    def _on_child_clicked(self, parent_idx: int, child_idx: int):
        self.selected_field_idx = parent_idx
        self.selected_child_idx = child_idx
        self.field_list.setCurrentRow(parent_idx)
        self.child_list.setCurrentRow(child_idx)
        self.tabs.setCurrentIndex(1)
        self._sync_ui_from_state()
        self.preview_widget.update_preview()

    # ============================================================
    # СИНХРОНИЗАЦИЯ UI И СОСТОЯНИЯ
    # ============================================================

    def _rebuild_field_list(self):
        self.field_list.blockSignals(True)
        current = self.field_list.currentRow()
        self.field_list.clear()
        for i, f in enumerate(self.project.fields):
            size_label = f"{f.width}{f.unit} × {f.height}{f.unit}"
            child_count = len(f.children)
            child_info = f" +{child_count} доч." if child_count > 0 else ""
            text = f"#{i + 1}  {size_label}{child_info}"

            item = QListWidgetItem()
            self.field_list.addItem(item)
            # ВАЖНО: lambda с захватом idx=i, чтобы каждый обработчик имел свой индекс
            widget = FieldListItem(text, lambda idx=i: self._on_delete_field(idx))
            item.setSizeHint(widget.sizeHint())
            self.field_list.setItemWidget(item, widget)

        if 0 <= current < self.field_list.count():
            self.field_list.setCurrentRow(current)
        self.field_list.blockSignals(False)

    def _rebuild_child_list(self):
        f = self._current_field()
        self.child_list.blockSignals(True)
        self.child_list.clear()
        if f:
            for i, cf in enumerate(f.children):
                text = f"⊞ {i + 1}  {cf.width}×{cf.height}см @ ({cf.x},{cf.y})"
                item = QListWidgetItem()
                self.child_list.addItem(item)
                widget = FieldListItem(text, lambda idx=i: self._on_delete_child(idx))
                item.setSizeHint(widget.sizeHint())
                self.child_list.setItemWidget(item, widget)
        if 0 <= self.selected_child_idx < self.child_list.count():
            self.child_list.setCurrentRow(self.selected_child_idx)
        self.child_list.blockSignals(False)

    def _sync_ui_from_state(self):
        f = self._current_field()
        if not f:
            return

        # Карта
        self.card_width.blockSignals(True)
        self.card_height.blockSignals(True)
        self.card_width.setValue(self.project.cardWidthCm)
        self.card_height.setValue(self.project.cardHeightCm)
        self.card_width.blockSignals(False)
        self.card_height.blockSignals(False)
        self.card_bg_color.set_color(self.project.cardBgColor)
        self.card_bg_hex.setText(self.project.cardBgColor)

        # Поле
        for sb, val in [(self.field_x, f.x), (self.field_y, f.y),
                        (self.field_width, f.width), (self.field_height, f.height)]:
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)

        if f.unit == "cm":
            self.unit_cm.setChecked(True)
        else:
            self.unit_px.setChecked(True)

        self.show_border.blockSignals(True)
        self.border_width.blockSignals(True)
        self.border_radius.blockSignals(True)
        self.show_border.setChecked(f.border.show)
        self.border_width.setValue(f.border.width)
        self.border_radius.setValue(f.border.radius)
        self.border_color.set_color(f.border.color)
        self.show_border.blockSignals(False)
        self.border_width.blockSignals(False)
        self.border_radius.blockSignals(False)

        self.field_text.blockSignals(True)
        self.field_text.setPlainText(f.text.content)
        self.field_text.blockSignals(False)

        self.font_size.blockSignals(True)
        self.font_size.setValue(f.text.fontSize)
        self.font_size.blockSignals(False)

        self.text_color.set_color(f.text.color)

        idx = self.font_family.findText(f.text.fontFamily)
        if idx >= 0:
            self.font_family.setCurrentIndex(idx)
        else:
            self.font_family.setEditText(f.text.fontFamily)

        pos_idx = {"center": 0, "top": 1, "bottom": 2}.get(f.text.position, 0)
        self.text_position.blockSignals(True)
        self.text_position.setCurrentIndex(pos_idx)
        self.text_position.blockSignals(False)

        align_x_idx = {"left": 0, "center": 1, "right": 2}.get(f.text.alignX, 1)
        self.text_align_x.blockSignals(True)
        self.text_align_x.setCurrentIndex(align_x_idx)
        self.text_align_x.blockSignals(False)

        self.img_fit.blockSignals(True)
        self.img_cover.blockSignals(True)
        self.img_fit.setChecked(f.imgFit)
        self.img_cover.setChecked(f.imgCover)
        self.img_fit.blockSignals(False)
        self.img_cover.blockSignals(False)

        img_x_idx = {"left": 0, "center": 1, "right": 2}.get(f.imgAlignX, 1)
        img_y_idx = {"top": 0, "center": 1, "bottom": 2}.get(f.imgAlignY, 1)
        self.img_align_x.blockSignals(True)
        self.img_align_y.blockSignals(True)
        self.img_align_x.setCurrentIndex(img_x_idx)
        self.img_align_y.setCurrentIndex(img_y_idx)
        self.img_align_x.blockSignals(False)
        self.img_align_y.blockSignals(False)

        self.remove_img_btn.setVisible(f.imageSrc is not None)

        # Дочерние поля
        self._rebuild_child_list()
        cf = self._current_child()
        self.child_editor.setVisible(cf is not None)

        if cf:
            for sb, val in [(self.child_x, cf.x), (self.child_y, cf.y),
                            (self.child_width, cf.width), (self.child_height, cf.height)]:
                sb.blockSignals(True)
                sb.setValue(val)
                sb.blockSignals(False)

            self.child_show_border.blockSignals(True)
            self.child_border_width.blockSignals(True)
            self.child_border_radius.blockSignals(True)
            self.child_show_border.setChecked(cf.border.show)
            self.child_border_width.setValue(cf.border.width)
            self.child_border_radius.setValue(cf.border.radius)
            self.child_border_color.set_color(cf.border.color)
            self.child_show_border.blockSignals(False)
            self.child_border_width.blockSignals(False)
            self.child_border_radius.blockSignals(False)

            self.child_text.blockSignals(True)
            self.child_text.setPlainText(cf.text.content)
            self.child_text.blockSignals(False)

            self.child_font_size.blockSignals(True)
            self.child_font_size.setValue(cf.text.fontSize)
            self.child_font_size.blockSignals(False)

            self.child_text_color.set_color(cf.text.color)

            idx = self.child_font_family.findText(cf.text.fontFamily)
            if idx >= 0:
                self.child_font_family.setCurrentIndex(idx)
            else:
                self.child_font_family.setEditText(cf.text.fontFamily)

            pos_idx = {"center": 0, "top": 1, "bottom": 2}.get(cf.text.position, 0)
            self.child_text_position.blockSignals(True)
            self.child_text_position.setCurrentIndex(pos_idx)
            self.child_text_position.blockSignals(False)

            align_x_idx = {"left": 0, "center": 1, "right": 2}.get(cf.text.alignX, 1)
            self.child_text_align_x.blockSignals(True)
            self.child_text_align_x.setCurrentIndex(align_x_idx)
            self.child_text_align_x.blockSignals(False)

            self.child_img_fit.blockSignals(True)
            self.child_img_cover.blockSignals(True)
            self.child_img_fit.setChecked(cf.imgFit)
            self.child_img_cover.setChecked(cf.imgCover)
            self.child_img_fit.blockSignals(False)
            self.child_img_cover.blockSignals(False)

            img_x_idx = {"left": 0, "center": 1, "right": 2}.get(cf.imgAlignX, 1)
            img_y_idx = {"top": 0, "center": 1, "bottom": 2}.get(cf.imgAlignY, 1)
            self.child_img_align_x.blockSignals(True)
            self.child_img_align_y.blockSignals(True)
            self.child_img_align_x.setCurrentIndex(img_x_idx)
            self.child_img_align_y.setCurrentIndex(img_y_idx)
            self.child_img_align_x.blockSignals(False)
            self.child_img_align_y.blockSignals(False)

            self.remove_child_img_btn.setVisible(cf.imageSrc is not None)

        self.preview_widget.selected_field_idx = self.selected_field_idx
        self.preview_widget.selected_child_idx = self.selected_child_idx

    def _update_info(self):
        self.info_card_size.setText(f"Размер карты: {self.project.cardWidthCm} × {self.project.cardHeightCm} см")
        self.info_field_count.setText(f"Кол-во полей: {len(self.project.fields)}")
        self.info_selected_field.setText(f"Выбрано поле: #{self.selected_field_idx + 1}")
        self.info_label.setText(f"Превью карты · {self.project.cardWidthCm} × {self.project.cardHeightCm} см")

    # ============================================================
    # СЕРИАЛИЗАЦИЯ
    # ============================================================

    def _project_to_dict(self) -> Dict:
        return {
            "version": 4,
            "cardWidthCm": self.project.cardWidthCm,
            "cardHeightCm": self.project.cardHeightCm,
            "cardBgColor": self.project.cardBgColor,
            "fields": [
                {
                    "id": f.id,
                    "x": f.x,
                    "y": f.y,
                    "unit": f.unit,
                    "width": f.width,
                    "height": f.height,
                    "border": asdict(f.border),
                    "text": asdict(f.text),
                    "imageSrc": f.imageSrc,
                    "imgFit": f.imgFit,
                    "imgCover": f.imgCover,
                    "imgAlignX": f.imgAlignX,
                    "imgAlignY": f.imgAlignY,
                    "children": [
                        {
                            "id": cf.id,
                            "x": cf.x,
                            "y": cf.y,
                            "width": cf.width,
                            "height": cf.height,
                            "border": asdict(cf.border),
                            "text": asdict(cf.text),
                            "imageSrc": cf.imageSrc,
                            "imgFit": cf.imgFit,
                            "imgCover": cf.imgCover,
                            "imgAlignX": cf.imgAlignX,
                            "imgAlignY": cf.imgAlignY,
                        }
                        for cf in f.children
                    ]
                }
                for f in self.project.fields
            ]
        }

    def _dict_to_project(self, data: Dict):
        self.project.cardWidthCm = data.get("cardWidthCm", 9.0)
        self.project.cardHeightCm = data.get("cardHeightCm", 6.0)
        self.project.cardBgColor = data.get("cardBgColor", "#ffffff")
        self.project.fields = []

        for f_data in data.get("fields", []):
            border_data = f_data.get("border", {})
            text_data = f_data.get("text", {})

            f = FieldConfig(
                id=f_data.get("id", str(uuid.uuid4())[:8]),
                x=f_data.get("x", 0.5),
                y=f_data.get("y", 0.5),
                unit=f_data.get("unit", "cm"),
                width=f_data.get("width", 8.0),
                height=f_data.get("height", 5.0),
                border=BorderConfig(
                    show=border_data.get("show", True),
                    width=border_data.get("width", 2.0),
                    radius=border_data.get("radius", 8.0),
                    color=border_data.get("color", "#1e293b"),
                ),
                text=TextConfig(
                    content=text_data.get("content", ""),
                    fontSize=text_data.get("fontSize", 14.0),
                    color=text_data.get("color", "#0f172a"),
                    fontFamily=text_data.get("fontFamily", "Arial"),
                    position=text_data.get("position", "center"),
                    alignX=text_data.get("alignX", "center"),
                ),
                imageSrc=f_data.get("imageSrc"),
                imgFit=f_data.get("imgFit", True),
                imgCover=f_data.get("imgCover", False),
                imgAlignX=f_data.get("imgAlignX", "center"),
                imgAlignY=f_data.get("imgAlignY", "center"),
                children=[],
            )

            for cf_data in f_data.get("children", []):
                cf_border = cf_data.get("border", {})
                cf_text = cf_data.get("text", {})
                cf = ChildFieldConfig(
                    id=cf_data.get("id", str(uuid.uuid4())[:8]),
                    x=cf_data.get("x", 0.5),
                    y=cf_data.get("y", 0.5),
                    width=cf_data.get("width", 4.0),
                    height=cf_data.get("height", 3.0),
                    border=BorderConfig(
                        show=cf_border.get("show", True),
                        width=cf_border.get("width", 1.0),
                        radius=cf_border.get("radius", 4.0),
                        color=cf_border.get("color", "#059669"),
                    ),
                    text=TextConfig(
                        content=cf_text.get("content", ""),
                        fontSize=cf_text.get("fontSize", 10.0),
                        color=cf_text.get("color", "#0f172a"),
                        fontFamily=cf_text.get("fontFamily", "Arial"),
                        position=cf_text.get("position", "center"),
                        alignX=cf_text.get("alignX", "center"),
                    ),
                    imageSrc=cf_data.get("imageSrc"),
                    imgFit=cf_data.get("imgFit", True),
                    imgCover=cf_data.get("imgCover", False),
                    imgAlignX=cf_data.get("imgAlignX", "center"),
                    imgAlignY=cf_data.get("imgAlignY", "center"),
                )
                f.children.append(cf)

            self.project.fields.append(f)


# ============================================================
# ТОЧКА ВХОДА
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Глобальная таблица стилей — с явными стрелочками для SpinBox
    app.setStyleSheet("""
        QMainWindow { background: #f1f5f9; }
        QWidget { font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 12px; }

        QSpinBox, QDoubleSpinBox {
            padding: 4px 22px 4px 8px;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            background: white;
        }
        QSpinBox:focus, QDoubleSpinBox:focus {
            border-color: #6366f1;
        }

        /* Стрелочки вверх/вниз */
        QDoubleSpinBox::up-button, QSpinBox::up-button {
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 18px;
            border: none;
            border-left: 1px solid #e2e8f0;
            background: #f8fafc;
        }
        QDoubleSpinBox::down-button, QSpinBox::down-button {
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 18px;
            border: none;
            border-left: 1px solid #e2e8f0;
            background: #f8fafc;
        }
        QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
        QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {
            background: #e2e8f0;
        }

        /* Треугольники-стрелки */
        QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {
            width: 0px;
            height: 0px;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-bottom: 5px solid #64748b;
        }
        QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid #64748b;
        }

        QComboBox, QLineEdit, QTextEdit {
            padding: 4px 8px;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            background: white;
        }
        QComboBox:focus, QLineEdit:focus, QTextEdit:focus {
            border-color: #6366f1;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
            background: #f8fafc;
        }
        QComboBox::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid #64748b;
        }

        QCheckBox { spacing: 6px; }
        QCheckBox::indicator {
            width: 16px; height: 16px;
            border: 1px solid #cbd5e1;
            border-radius: 3px;
            background: white;
        }
        QCheckBox::indicator:checked {
            background: #6366f1;
            border-color: #6366f1;
        }
        QRadioButton::indicator {
            width: 16px; height: 16px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            background: white;
        }
        QRadioButton::indicator:checked {
            background: #6366f1;
            border-color: #6366f1;
        }
        QGroupBox {
            font-weight: bold;
            font-size: 11px;
            color: #64748b;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QScrollArea { border: none; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()