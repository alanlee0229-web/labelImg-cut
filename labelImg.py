#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import codecs
import os.path
import platform
import shutil
import sys
import webbrowser as wb
from functools import partial

import cv2
import numpy as np
import random

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    # needed for py3+qt4
    # Ref:
    # http://pyqt.sourceforge.net/Docs/PyQt4/incompatible_apis.html
    # http://stackoverflow.com/questions/21217399/pyqt4-qtcore-qvariant-object-instead-of-a-string
    if sys.version_info.major >= 3:
        import sip

        sip.setapi('QVariant', 2)
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

from libs.combobox import ComboBox
from libs.default_label_combobox import DefaultLabelComboBox
from libs.resources import *
from libs.constants import *
from libs.utils import *
from libs.settings import Settings
from libs.shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.stringBundle import StringBundle
from libs.canvas import Canvas
from libs.zoomWidget import ZoomWidget
from libs.lightWidget import LightWidget
from libs.labelDialog import LabelDialog
from libs.colorDialog import ColorDialog
from libs.labelFile import LabelFile, LabelFileError, LabelFileFormat
from libs.toolBar import ToolBar
from libs.pascal_voc_io import PascalVocReader
from libs.pascal_voc_io import XML_EXT
from libs.yolo_io import YoloReader
from libs.yolo_io import TXT_EXT
from libs.create_ml_io import CreateMLReader
from libs.create_ml_io import JSON_EXT
from libs.ustr import ustr
from libs.hashableQListWidgetItem import HashableQListWidgetItem

__appname__ = 'labelImg'


class WindowMixin(object):

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            add_actions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            add_actions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, default_filename=None, default_prefdef_class_file=None, default_save_dir=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        # Load setting in the main thread
        self.settings = Settings()
        self.settings.load()
        settings = self.settings

        self.os_name = platform.system()

        # Load string bundle for i18n
        self.string_bundle = StringBundle.get_bundle()
        get_str = lambda str_id: self.string_bundle.get_string(str_id)

        # Save as Pascal voc xml
        self.default_save_dir = default_save_dir
        self.label_file_format = settings.get(SETTING_LABEL_FILE_FORMAT, LabelFileFormat.PASCAL_VOC)

        # For loading all image under a directory
        self.m_img_list = []
        self.dir_name = None
        self.label_hist = []
        self.last_open_dir = None
        self.cur_img_idx = 0
        self.img_count = len(self.m_img_list)

        # Whether we need to save or not.
        self.dirty = False

        self._no_selection_slot = False
        self._beginner = True
        self.screencast = "https://youtu.be/p0nR2YsCY_U"
        self.all_selected_mode = False  # 全选模式标志

        # Load predefined classes to the list
        self.load_predefined_classes(default_prefdef_class_file)

        if self.label_hist:
            self.default_label = self.label_hist[0]
        else:
            print("Not find:/data/predefined_classes.txt (optional)")

        # Main widgets and related state.
        self.label_dialog = LabelDialog(parent=self, list_item=self.label_hist)

        self.items_to_shapes = {}
        self.shapes_to_items = {}
        self.prev_label_text = ''

        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(0, 0, 0, 0)

        # Create a widget for using default label
        self.use_default_label_checkbox = QCheckBox(get_str('useDefaultLabel'))
        self.use_default_label_checkbox.setChecked(False)
        self.default_label_combo_box = DefaultLabelComboBox(self, items=self.label_hist)

        use_default_label_qhbox_layout = QHBoxLayout()
        use_default_label_qhbox_layout.addWidget(self.use_default_label_checkbox)
        use_default_label_qhbox_layout.addWidget(self.default_label_combo_box)
        use_default_label_container = QWidget()
        use_default_label_container.setLayout(use_default_label_qhbox_layout)

        # Create a widget for edit and diffc button
        self.diffc_button = QCheckBox(get_str('useDifficult'))
        self.diffc_button.setChecked(False)
        self.diffc_button.stateChanged.connect(self.button_state)
        self.edit_button = QToolButton()
        self.edit_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Add some of widgets to list_layout
        list_layout.addWidget(self.edit_button)
        list_layout.addWidget(self.diffc_button)
        list_layout.addWidget(use_default_label_container)

        # Create and add combobox for showing unique labels in group
        self.combo_box = ComboBox(self)
        list_layout.addWidget(self.combo_box)

                # 重构布局 - 按照1、2、3、4、5的正确顺序重新排列
        
        # 第一部分：雾气检测功能（可折叠菜单栏）
        fog_group_box = QGroupBox("1. 雾气检测功能")
        fog_group_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;color:black;}")
        fog_group_box.setCheckable(True)
        fog_group_box.setChecked(False)  # 默认折叠
        fog_group_box.setMaximumHeight(30)  # 折叠时的高度
        
        fog_layout = QVBoxLayout()
        fog_layout.setContentsMargins(5, 5, 5, 5)
        
        # 雾气检测标签
        self.fog_detection_label = QLabel(get_str('detectFog'))
        self.fog_detection_label.setAlignment(Qt.AlignCenter)
        self.fog_detection_label.setStyleSheet("QLabel{background-color:lightgray;color:black;font-size:18px;font-weight:bold;border-radius:3px;padding:3px;}")
        fog_layout.addWidget(self.fog_detection_label)
        
        # 雾气检测结果标签
        self.fog_result_label = QLabel(get_str('fogResult'))
        self.fog_result_label.setAlignment(Qt.AlignCenter)
        self.fog_result_label.setStyleSheet("QLabel{background-color:white;color:red;font-size:18px;font-weight:bold;border-radius:5px;padding:5px;}")
        fog_layout.addWidget(self.fog_result_label)
        
        # 根据有雾标签生成视频标签按钮
        self.generate_video_label_button = QPushButton('根据有雾标签生成视频标签')
        self.generate_video_label_button.setStyleSheet("QPushButton{background-color:lightgray;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:6px;}")
        self.generate_video_label_button.setFixedHeight(30)
        self.generate_video_label_button.clicked.connect(self.generate_video_label)
        fog_layout.addWidget(self.generate_video_label_button)
        
        # 提取有雾训练数据按钮
        self.extract_train_data_button = QPushButton('提取有雾训练数据')
        self.extract_train_data_button.setStyleSheet("QPushButton{background-color:lightgray;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:6px;}")
        self.extract_train_data_button.setFixedHeight(30)
        self.extract_train_data_button.clicked.connect(self.extract_train_data)
        fog_layout.addWidget(self.extract_train_data_button)
        
        # 阈值设置
        self.fog_threshold_label = QLabel('生成视频标签的有雾阈值:')
        self.fog_threshold_label.setAlignment(Qt.AlignCenter)
        self.fog_threshold_label.setStyleSheet("QLabel{background-color:white;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:5px;}")
        
        self.fog_threshold_edit = QLineEdit("12.0")
        self.fog_threshold_edit.setValidator(QDoubleValidator())
        self.fog_threshold_edit.setFixedWidth(200)
        self.fog_threshold_edit.setStyleSheet("QLineEdit{background-color:white;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:5px;}")
        self.fog_threshold_edit.setFixedHeight(30)
        self.fog_threshold_edit.setAlignment(Qt.AlignCenter)
        
        # 阈值设置水平布局
        self.h_layout = QHBoxLayout()
        self.h_layout.addWidget(self.fog_threshold_label)
        self.h_layout.addWidget(self.fog_threshold_edit)
        fog_layout.addLayout(self.h_layout)
        
        # 根据阈值生成视频标签按钮
        self.generate_video_label_with_fog_threshold_button = QPushButton('根据阈值生成视频标签')
        self.generate_video_label_with_fog_threshold_button.setStyleSheet("QPushButton{background-color:lightgray;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:6px;}")
        self.generate_video_label_with_fog_threshold_button.setFixedHeight(30)
        self.generate_video_label_with_fog_threshold_button.clicked.connect(self.generate_video_label_with_fog_threshold)
        fog_layout.addWidget(self.generate_video_label_with_fog_threshold_button)
        
        # 提取阈值有雾训练数据按钮
        self.extract_train_data_with_fog_threshold_button = QPushButton('提取阈值有雾训练数据')
        self.extract_train_data_with_fog_threshold_button.setStyleSheet("QPushButton{background-color:lightgray;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:6px;}")
        self.extract_train_data_with_fog_threshold_button.setFixedHeight(30)
        self.extract_train_data_with_fog_threshold_button.clicked.connect(self.extract_train_data_with_fog_threshold)
        fog_layout.addWidget(self.extract_train_data_with_fog_threshold_button)
        
        fog_group_box.setLayout(fog_layout)
        list_layout.addWidget(fog_group_box)
        
        # 连接折叠/展开信号
        fog_group_box.toggled.connect(lambda checked: self.toggle_group_box(fog_group_box, checked))
        
        # 第二部分：区块大小设置
        # 先定义所有需要的控件
        self.block_size_label = QLabel('创建区块初始大小:')
        self.block_size_label.setAlignment(Qt.AlignCenter)
        self.block_size_label.setStyleSheet(
            "QLabel{background-color:white;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:5px;}")

        # 宽度输入框
        self.block_width_label = QLabel('宽:')
        self.block_width_label.setStyleSheet(
            "QLabel{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        
        self.block_width_edit = QLineEdit("35")
        self.block_width_edit.setValidator(QIntValidator(10, 1000))
        self.block_width_edit.setFixedWidth(60)
        self.block_width_edit.setStyleSheet(
            "QLineEdit{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        self.block_width_edit.setFixedHeight(25)
        self.block_width_edit.setAlignment(Qt.AlignCenter)

        # 高度输入框
        self.block_height_label = QLabel('高:')
        self.block_height_label.setStyleSheet(
            "QLabel{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        
        self.block_height_edit = QLineEdit("35")
        self.block_height_edit.setValidator(QIntValidator(10, 1000))
        self.block_height_edit.setFixedWidth(60)
        self.block_height_edit.setStyleSheet(
            "QLineEdit{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        self.block_height_edit.setFixedHeight(25)
        self.block_height_edit.setAlignment(Qt.AlignCenter)
        
        # 创建GroupBox和布局
        block_size_group_box = QGroupBox("2. 区块大小设置")
        block_size_group_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;color:black;}")
        
        block_size_layout = QHBoxLayout()
        block_size_layout.setContentsMargins(5, 5, 5, 5)
        
        block_size_layout.addWidget(self.block_size_label)
        block_size_layout.addWidget(self.block_width_label)
        block_size_layout.addWidget(self.block_width_edit)
        block_size_layout.addWidget(self.block_height_label)
        block_size_layout.addWidget(self.block_height_edit)
        
        # 添加统一按钮
        self.unify_bbox_size_button = QPushButton('统一')
        self.unify_bbox_size_button.setStyleSheet(
            "QPushButton{background-color:lightblue;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:4px;}")
        self.unify_bbox_size_button.setFixedHeight(25)
        self.unify_bbox_size_button.clicked.connect(self.unify_bbox_sizes)
        block_size_layout.addWidget(self.unify_bbox_size_button)
        
        block_size_group_box.setLayout(block_size_layout)
        list_layout.addWidget(block_size_group_box)

        # 第三部分：检测框切割功能
        cut_bbox_group_box = QGroupBox("3. 检测框切割功能")
        cut_bbox_group_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;color:black;}")
        
        cut_bbox_layout = QHBoxLayout()
        cut_bbox_layout.setContentsMargins(5, 5, 5, 5)
        
        # 添加创建固定区块按钮
        self.add_block_button = QPushButton('固定区块模式Q')
        self.add_block_button.setStyleSheet(
            "QPushButton{background-color:lightgreen;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:4px;}")
        self.add_block_button.setFixedHeight(25)
        self.add_block_button.clicked.connect(self.add_fixed_size_block)
        
        # 添加创建不规则选区按钮
        self.add_freehand_block_button = QPushButton('自定义选区模式E')
        self.add_freehand_block_button.setStyleSheet(
            "QPushButton{background-color:lightyellow;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:4px;}")
        self.add_freehand_block_button.setFixedHeight(25)
        self.add_freehand_block_button.clicked.connect(self.add_freehand_block)
        
        # 添加切割按钮
        self.cut_bbox_button = QPushButton('切割检测框C')
        self.cut_bbox_button.setStyleSheet(
            "QPushButton{background-color:orange;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:4px;}")
        self.cut_bbox_button.setFixedHeight(25)
        self.cut_bbox_button.clicked.connect(self.cut_selected_bbox)
        
        # 添加控件到布局
        cut_bbox_layout.addWidget(self.add_block_button)
        cut_bbox_layout.addWidget(self.add_freehand_block_button)
        cut_bbox_layout.addWidget(self.cut_bbox_button)
        
        cut_bbox_group_box.setLayout(cut_bbox_layout)
        list_layout.addWidget(cut_bbox_group_box)
        
        # 第四部分：提取类别0标签功能
        extract_class0_group_box = QGroupBox("4. 提取类别0标签功能")
        extract_class0_group_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;color:black;}")
        
        extract_class0_layout = QVBoxLayout()
        extract_class0_layout.setContentsMargins(5, 5, 5, 5)
        
        # 添加提取类别0标签的功能按钮
        self.extract_class0_button = QPushButton('提取类别0标签文件')
        self.extract_class0_button.setStyleSheet("QPushButton{background-color:lightgreen;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:6px;}")
        self.extract_class0_button.setFixedHeight(30)
        self.extract_class0_button.clicked.connect(self.extract_class0_labels)
        extract_class0_layout.addWidget(self.extract_class0_button)
        
        extract_class0_group_box.setLayout(extract_class0_layout)
        list_layout.addWidget(extract_class0_group_box)
        
        # 第五部分：图像复制和检测框保留功能
        image_copy_group_box = QGroupBox("5. 图像复制和检测框保留")
        image_copy_group_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;color:black;}")
        
        image_copy_layout = QHBoxLayout()
        image_copy_layout.setContentsMargins(5, 5, 5, 5)
        
        # 添加图像复制按钮
        self.copy_images_with_bbox_button = QPushButton('自动复制图像和检测框')
        self.copy_images_with_bbox_button.setStyleSheet(
            "QPushButton{background-color:lightgreen;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:4px;}")
        self.copy_images_with_bbox_button.setFixedHeight(25)
        self.copy_images_with_bbox_button.clicked.connect(self.copy_images_with_bbox)
        image_copy_layout.addWidget(self.copy_images_with_bbox_button)
        
        # 添加复制数量标签和输入框
        self.copy_count_label_2 = QLabel('复制数量:')
        self.copy_count_label_2.setStyleSheet(
            "QLabel{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        image_copy_layout.addWidget(self.copy_count_label_2)
        
        self.copy_count_edit_2 = QLineEdit("1")
        self.copy_count_edit_2.setValidator(QIntValidator(1, 100))
        self.copy_count_edit_2.setFixedWidth(60)
        self.copy_count_edit_2.setStyleSheet(
            "QLineEdit{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        self.copy_count_edit_2.setFixedHeight(25)
        self.copy_count_edit_2.setAlignment(Qt.AlignCenter)
        image_copy_layout.addWidget(self.copy_count_edit_2)
        
        # 添加检测框保留百分比标签和输入框
        self.bbox_keep_label = QLabel('保留%:')
        self.bbox_keep_label.setStyleSheet(
            "QLabel{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        image_copy_layout.addWidget(self.bbox_keep_label)
        
        self.bbox_keep_edit = QLineEdit("80")
        self.bbox_keep_edit.setValidator(QIntValidator(1, 100))
        self.bbox_keep_edit.setFixedWidth(60)
        self.bbox_keep_edit.setStyleSheet(
            "QLineEdit{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        self.bbox_keep_edit.setFixedHeight(25)
        self.bbox_keep_edit.setAlignment(Qt.AlignCenter)
        image_copy_layout.addWidget(self.bbox_keep_edit)
        
        image_copy_group_box.setLayout(image_copy_layout)
        list_layout.addWidget(image_copy_group_box)
        
        # 第五部分：复制检测框功能
        copy_bbox_group_box = QGroupBox("5. 复制检测框功能")
        copy_bbox_group_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;color:black;}")
        
        copy_bbox_layout = QVBoxLayout()
        copy_bbox_layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建水平布局来放置两个复制按钮
        copy_buttons_layout = QHBoxLayout()
        
        # 添加复制检测框到其他图像的功能按钮
        self.copy_bbox_to_others_button = QPushButton('复制检测框到其他图像')
        self.copy_bbox_to_others_button.setStyleSheet("QPushButton{background-color:lightblue;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:6px;}")
        self.copy_bbox_to_others_button.setFixedHeight(30)
        self.copy_bbox_to_others_button.clicked.connect(self.copy_bbox_to_other_images)
        self.copy_bbox_to_others_button.setEnabled(False)  # 初始状态禁用
        copy_buttons_layout.addWidget(self.copy_bbox_to_others_button)

        # 添加随机复制目录检测框的功能按钮
        self.copy_all_bbox_randomly_button = QPushButton('随机复制目录检测框')
        self.copy_all_bbox_randomly_button.setStyleSheet("QPushButton{background-color:orange;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:6px;}")
        self.copy_all_bbox_randomly_button.setFixedHeight(30)
        self.copy_all_bbox_randomly_button.clicked.connect(self.copy_all_bbox_randomly)
        self.copy_all_bbox_randomly_button.setEnabled(False)  # 初始状态禁用
        copy_buttons_layout.addWidget(self.copy_all_bbox_randomly_button)
        
        copy_bbox_layout.addLayout(copy_buttons_layout)

        # 复制数量设置
        self.copy_count_label = QLabel('复制到图像数量:')
        self.copy_count_label.setAlignment(Qt.AlignCenter)
        self.copy_count_label.setStyleSheet("QLabel{background-color:white;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:5px;}")

        self.copy_count_edit = QLineEdit("5")
        self.copy_count_edit.setValidator(QIntValidator(1, 1000))
        self.copy_count_edit.setFixedWidth(80)
        self.copy_count_edit.setStyleSheet("QLineEdit{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:6px;padding:5px;}")
        self.copy_count_edit.setFixedHeight(28)
        self.copy_count_edit.setAlignment(Qt.AlignCenter)

        # 创建水平布局来放置标签和输入框
        self.copy_count_layout = QHBoxLayout()
        self.copy_count_layout.addWidget(self.copy_count_label)
        self.copy_count_layout.addWidget(self.copy_count_edit)
        copy_bbox_layout.addLayout(self.copy_count_layout)
        
        copy_bbox_group_box.setLayout(copy_bbox_layout)
        list_layout.addWidget(copy_bbox_group_box)
        
        # 第六部分：图像旋转增强功能
        rotation_aug_group_box = QGroupBox("6. 图像旋转增强")
        rotation_aug_group_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;color:black;}")
        
        rotation_aug_layout = QVBoxLayout()
        rotation_aug_layout.setContentsMargins(5, 5, 5, 5)
        
        # 旋转增强标签
        self.rotation_aug_label = QLabel('图像旋转增强:')
        self.rotation_aug_label.setAlignment(Qt.AlignCenter)
        self.rotation_aug_label.setStyleSheet("QLabel{background-color:lightyellow;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:5px;}")
        
        # 增强数量输入框
        self.aug_count_label = QLabel('增强数量:')
        self.aug_count_label.setStyleSheet("QLabel{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        
        self.aug_count_edit = QLineEdit("3")
        self.aug_count_edit.setValidator(QIntValidator(1, 20))
        self.aug_count_edit.setFixedWidth(60)
        self.aug_count_edit.setStyleSheet("QLineEdit{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        self.aug_count_edit.setFixedHeight(25)
        self.aug_count_edit.setAlignment(Qt.AlignCenter)
        
        # 旋转角度范围输入框
        self.rotation_range_label = QLabel('角度范围:')
        self.rotation_range_label.setStyleSheet("QLabel{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        
        self.rotation_range_edit = QLineEdit("30")
        self.rotation_range_edit.setValidator(QIntValidator(1, 180))
        self.rotation_range_edit.setFixedWidth(60)
        self.rotation_range_edit.setStyleSheet("QLineEdit{background-color:white;color:black;font-size:12px;font-weight:bold;border-radius:4px;padding:3px;}")
        self.rotation_range_edit.setFixedHeight(25)
        self.rotation_range_edit.setAlignment(Qt.AlignCenter)
        
        # 旋转增强按钮
        self.rotation_aug_button = QPushButton('生成旋转增强图像')
        self.rotation_aug_button.setStyleSheet("QPushButton{background-color:lightgreen;color:black;font-size:14px;font-weight:bold;border-radius:6px;padding:6px;}")
        self.rotation_aug_button.setFixedHeight(30)
        self.rotation_aug_button.clicked.connect(self.generate_rotation_augmentation)
        
        # 旋转增强设置水平布局
        rotation_aug_settings_layout = QHBoxLayout()
        rotation_aug_settings_layout.addWidget(self.rotation_aug_label)
        rotation_aug_settings_layout.addWidget(self.aug_count_label)
        rotation_aug_settings_layout.addWidget(self.aug_count_edit)
        rotation_aug_settings_layout.addWidget(self.rotation_range_label)
        rotation_aug_settings_layout.addWidget(self.rotation_range_edit)
        rotation_aug_layout.addLayout(rotation_aug_settings_layout)
        
        # 旋转增强按钮
        rotation_aug_layout.addWidget(self.rotation_aug_button)
        
        rotation_aug_group_box.setLayout(rotation_aug_layout)
        list_layout.addWidget(rotation_aug_group_box)
        
        # Create and add a widget for showing current label items
        self.label_list = QListWidget()
        label_list_container = QWidget()
        label_list_container.setLayout(list_layout)
        self.label_list.itemActivated.connect(self.label_selection_changed)
        self.label_list.itemSelectionChanged.connect(self.label_selection_changed)
        self.label_list.itemDoubleClicked.connect(self.edit_label)
        # Connect to itemChanged to detect checkbox changes.
        self.label_list.itemChanged.connect(self.label_item_changed)
        list_layout.addWidget(self.label_list)

        self.dock = QDockWidget(get_str('boxLabelText'), self)
        self.dock.setObjectName(get_str('labels'))
        self.dock.setWidget(label_list_container)

        # 文件列表区域（变大）
        self.file_list_widget = QListWidget()
        self.file_list_widget.itemDoubleClicked.connect(self.file_item_double_clicked)
        self.file_list_widget.setMinimumHeight(300)  # 设置最小高度，让文件列表变大
        
        file_list_layout = QVBoxLayout()
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.addWidget(self.file_list_widget)
        file_list_container = QWidget()
        file_list_container.setLayout(file_list_layout)
        self.file_dock = QDockWidget(get_str('fileList'), self)
        self.file_dock.setObjectName(get_str('files'))
        self.file_dock.setWidget(file_list_container)

        self.zoom_widget = ZoomWidget()
        self.light_widget = LightWidget(get_str('lightWidgetTitle'))
        self.color_dialog = ColorDialog(parent=self)

        self.canvas = Canvas(parent=self)
        self.canvas.zoomRequest.connect(self.zoom_request)
        self.canvas.lightRequest.connect(self.light_request)
        self.canvas.set_drawing_shape_to_square(settings.get(SETTING_DRAW_SQUARE, False))

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scroll_bars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.scroll_area = scroll
        self.canvas.scrollRequest.connect(self.scroll_request)

        self.canvas.newShape.connect(self.new_shape)
        self.canvas.shapeMoved.connect(self.set_dirty)
        self.canvas.selectionChanged.connect(self.shape_selection_changed)
        self.canvas.drawingPolygon.connect(self.toggle_drawing_sensitive)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.file_dock)
        self.file_dock.setFeatures(QDockWidget.DockWidgetFloatable)

        self.dock_features = QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetFloatable
        self.dock.setFeatures(self.dock.features() ^ self.dock_features)

        # Actions
        action = partial(new_action, self)
        quit = action(get_str('quit'), self.close,
                      'Ctrl+Q', 'quit', get_str('quitApp'))

        open = action(get_str('openFile'), self.open_file,
                      'Ctrl+O', 'open', get_str('openFileDetail'))

        open_dir = action(get_str('openDir'), self.open_dir_dialog,
                          'Ctrl+u', 'open', get_str('openDir'))

        change_save_dir = action(get_str('changeSaveDir'), self.change_save_dir_dialog,
                                 'Ctrl+r', 'open', get_str('changeSavedAnnotationDir'))

        open_annotation = action(get_str('openAnnotation'), self.open_annotation_dialog,
                                 'Ctrl+Shift+O', 'open', get_str('openAnnotationDetail'))
        copy_prev_bounding = action(get_str('copyPrevBounding'), self.copy_previous_bounding_boxes, 'Ctrl+v', 'copy',
                                    get_str('copyPrevBounding'))

        open_next_image = action(get_str('nextImg'), self.open_next_image,
                                 'd', 'next', get_str('nextImgDetail'))

        open_prev_image = action(get_str('prevImg'), self.open_prev_image,
                                 'a', 'prev', get_str('prevImgDetail'))

        verify = action(get_str('verifyImg'), self.verify_image,
                        'space', 'verify', get_str('verifyImgDetail'))

        save = action(get_str('save'), self.save_file,
                      'Ctrl+S', 'save', get_str('saveDetail'), enabled=False)

        def get_format_meta(format):
            """
            returns a tuple containing (title, icon_name) of the selected format
            """
            if format == LabelFileFormat.PASCAL_VOC:
                return '&PascalVOC', 'format_voc'
            elif format == LabelFileFormat.YOLO:
                return '&YOLO', 'format_yolo'
            elif format == LabelFileFormat.CREATE_ML:
                return '&CreateML', 'format_createml'

        save_format = action(get_format_meta(self.label_file_format)[0],
                             self.change_format, 'Ctrl+Y',
                             get_format_meta(self.label_file_format)[1],
                             get_str('changeSaveFormat'), enabled=True)

        save_as = action(get_str('saveAs'), self.save_file_as,
                         'Ctrl+Shift+S', 'save-as', get_str('saveAsDetail'), enabled=False)

        close = action(get_str('closeCur'), self.close_file, 'Ctrl+W', 'close', get_str('closeCurDetail'))

        delete_image = action(get_str('deleteImg'), self.delete_image, 'Ctrl+Shift+D', 'close',
                              get_str('deleteImgDetail'))

        reset_all = action(get_str('resetAll'), self.reset_all, None, 'resetall', get_str('resetAllDetail'))

        color1 = action(get_str('boxLineColor'), self.choose_color1,
                        'Ctrl+L', 'color_line', get_str('boxLineColorDetail'))

        create_mode = action(get_str('crtBox'), self.set_create_mode,
                             'w', 'new', get_str('crtBoxDetail'), enabled=False)
        edit_mode = action(get_str('editBox'), self.set_edit_mode,
                           'Ctrl+J', 'edit', get_str('editBoxDetail'), enabled=False)

        create = action(get_str('crtBox'), self.create_shape,
                        'w', 'new', get_str('crtBoxDetail'), enabled=False)
        delete = action(get_str('delBox'), self.delete_selected_shape,
                        'Delete', 'delete', get_str('delBoxDetail'), enabled=False)
        copy = action(get_str('dupBox'), self.copy_selected_shape,
                      'Ctrl+D', 'copy', get_str('dupBoxDetail'),
                      enabled=False)

        advanced_mode = action(get_str('advancedMode'), self.toggle_advanced_mode,
                               None, 'expert', get_str('advancedModeDetail'),
                               checkable=True)
        
        select_all = action("全选删除", self.select_all_shapes,
                           'Ctrl+Shift+A', 'selectall', "全选并删除所有检测框",
                           enabled=False)

        hide_all = action(get_str('hideAllBox'), partial(self.toggle_polygons, False),
                          'Ctrl+H', 'hide', get_str('hideAllBoxDetail'),
                          enabled=False)
        show_all = action(get_str('showAllBox'), partial(self.toggle_polygons, True),
                          'Ctrl+A', 'hide', get_str('showAllBoxDetail'),
                          enabled=False)

        help_default = action(get_str('tutorialDefault'), self.show_default_tutorial_dialog, None, 'help',
                              get_str('tutorialDetail'))
        show_info = action(get_str('info'), self.show_info_dialog, None, 'help', get_str('info'))
        show_shortcut = action(get_str('shortcut'), self.show_shortcuts_dialog, None, 'help', get_str('shortcut'))

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoom_widget)
        self.zoom_widget.setWhatsThis(
            u"Zoom in or out of the image. Also accessible with"
            " %s and %s from the canvas." % (format_shortcut("Ctrl+[-+]"),
                                             format_shortcut("Ctrl+Wheel")))
        self.zoom_widget.setEnabled(False)

        zoom_in = action(get_str('zoomin'), partial(self.add_zoom, 10),
                         'Ctrl++', 'zoom-in', get_str('zoominDetail'), enabled=False)
        zoom_out = action(get_str('zoomout'), partial(self.add_zoom, -10),
                          'Ctrl+-', 'zoom-out', get_str('zoomoutDetail'), enabled=False)
        zoom_org = action(get_str('originalsize'), partial(self.set_zoom, 100),
                          'Ctrl+=', 'zoom', get_str('originalsizeDetail'), enabled=False)
        fit_window = action(get_str('fitWin'), self.set_fit_window,
                            'Ctrl+F', 'fit-window', get_str('fitWinDetail'),
                            checkable=True, enabled=False)
        fit_width = action(get_str('fitWidth'), self.set_fit_width,
                           'Ctrl+Shift+F', 'fit-width', get_str('fitWidthDetail'),
                           checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoom_actions = (self.zoom_widget, zoom_in, zoom_out,
                        zoom_org, fit_window, fit_width)
        self.zoom_mode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scale_fit_window,
            self.FIT_WIDTH: self.scale_fit_width,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        light = QWidgetAction(self)
        light.setDefaultWidget(self.light_widget)
        self.light_widget.setWhatsThis(
            u"Brighten or darken current image. Also accessible with"
            " %s and %s from the canvas." % (format_shortcut("Ctrl+Shift+[-+]"),
                                             format_shortcut("Ctrl+Shift+Wheel")))
        self.light_widget.setEnabled(False)

        light_brighten = action(get_str('lightbrighten'), partial(self.add_light, 10),
                                'Ctrl+Shift++', 'light_lighten', get_str('lightbrightenDetail'), enabled=False)
        light_darken = action(get_str('lightdarken'), partial(self.add_light, -10),
                              'Ctrl+Shift+-', 'light_darken', get_str('lightdarkenDetail'), enabled=False)
        light_org = action(get_str('lightreset'), partial(self.set_light, 50),
                           'Ctrl+Shift+=', 'light_reset', get_str('lightresetDetail'), checkable=True, enabled=False)
        light_org.setChecked(True)

        # Group light controls into a list for easier toggling.
        light_actions = (self.light_widget, light_brighten,
                         light_darken, light_org)

        edit = action(get_str('editLabel'), self.edit_label,
                      'Ctrl+E', 'edit', get_str('editLabelDetail'),
                      enabled=False)
        self.edit_button.setDefaultAction(edit)

        shape_line_color = action(get_str('shapeLineColor'), self.choose_shape_line_color,
                                  icon='color_line', tip=get_str('shapeLineColorDetail'),
                                  enabled=False)
        shape_fill_color = action(get_str('shapeFillColor'), self.choose_shape_fill_color,
                                  icon='color', tip=get_str('shapeFillColorDetail'),
                                  enabled=False)

        labels = self.dock.toggleViewAction()
        labels.setText(get_str('showHide'))
        labels.setShortcut('Ctrl+Shift+L')

        # Label list context menu.
        label_menu = QMenu()
        add_actions(label_menu, (edit, delete))
        self.label_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.label_list.customContextMenuRequested.connect(
            self.pop_label_list_menu)

        # Draw squares/rectangles
        self.draw_squares_option = QAction(get_str('drawSquares'), self)
        self.draw_squares_option.setShortcut('Ctrl+Shift+R')
        self.draw_squares_option.setCheckable(True)
        self.draw_squares_option.setChecked(settings.get(SETTING_DRAW_SQUARE, False))
        self.draw_squares_option.triggered.connect(self.toggle_draw_square)

        # 添加新的动作：切换固定和不规则功能快捷键说明
        self.toggle_drawing_mode_action = QAction("切换固定和不规则功能快捷键 (Q/E)", self)
        self.toggle_drawing_mode_action.setToolTip("按Q键切换到固定尺寸模式，按E键切换到不规则尺寸模式")
        
        # 添加全选删除检测框动作
        self.select_all_action = QAction("全选删除", self)
        self.select_all_action.setShortcut("Ctrl+Shift+A")
        self.select_all_action.triggered.connect(self.select_all_shapes)
        
        # Store actions for further handling.
        self.actions = Struct(save=save, save_format=save_format, saveAs=save_as, open=open, close=close,
                              resetAll=reset_all, deleteImg=delete_image,
                              lineColor=color1, create=create, delete=delete, edit=edit, copy=copy,
                              createMode=create_mode, editMode=edit_mode, advancedMode=advanced_mode,
                              shapeLineColor=shape_line_color, shapeFillColor=shape_fill_color,
                              zoom=zoom, zoomIn=zoom_in, zoomOut=zoom_out, zoomOrg=zoom_org,
                              fitWindow=fit_window, fitWidth=fit_width,
                              zoomActions=zoom_actions,
                              lightBrighten=light_brighten, lightDarken=light_darken, lightOrg=light_org,
                              lightActions=light_actions,
                              fileMenuActions=(
                                  open, open_dir, save, save_as, close, reset_all, quit),
                              beginner=(), advanced=(),
                              editMenu=(edit, copy, delete, self.select_all_action,
                                        None, color1, self.draw_squares_option, self.toggle_drawing_mode_action),
                              beginnerContext=(create, edit, copy, delete),
                              advancedContext=(create_mode, edit_mode, edit, copy,
                                               delete, shape_line_color, shape_fill_color),
                              onLoadActive=(
                                  close, create, create_mode, edit_mode),
                              onShapesPresent=(save_as, hide_all, show_all))

        self.menus = Struct(
            file=self.menu(get_str('menu_file')),
            edit=self.menu(get_str('menu_edit')),
            view=self.menu(get_str('menu_view')),
            help=self.menu(get_str('menu_help')),
            recentFiles=QMenu(get_str('menu_openRecent')),
            labelList=label_menu)

        # Auto saving : Enable auto saving if pressing next
        self.auto_saving = QAction(get_str('autoSaveMode'), self)
        self.auto_saving.setCheckable(True)
        self.auto_saving.setChecked(settings.get(SETTING_AUTO_SAVE, False))
        # Sync single class mode from PR#106
        self.single_class_mode = QAction(get_str('singleClsMode'), self)
        self.single_class_mode.setShortcut("Ctrl+Shift+S")
        self.single_class_mode.setCheckable(True)
        self.single_class_mode.setChecked(settings.get(SETTING_SINGLE_CLASS, False))
        self.lastLabel = None
        # Add option to enable/disable labels being displayed at the top of bounding boxes
        self.display_label_option = QAction(get_str('displayLabel'), self)
        self.display_label_option.setShortcut("Ctrl+Shift+P")
        self.display_label_option.setCheckable(True)
        self.display_label_option.setChecked(settings.get(SETTING_PAINT_LABEL, False))
        self.display_label_option.triggered.connect(self.toggle_paint_labels_option)

        add_actions(self.menus.file,
                    (open, open_dir, change_save_dir, open_annotation, copy_prev_bounding, self.menus.recentFiles, save,
                     save_format, save_as, close, reset_all, delete_image, quit))
        add_actions(self.menus.help, (help_default, show_info, show_shortcut))
        add_actions(self.menus.view, (
            self.auto_saving,
            self.single_class_mode,
            self.display_label_option,
            labels, advanced_mode, None,
            hide_all, show_all, None,
            zoom_in, zoom_out, zoom_org, None,
            fit_window, fit_width, None,
            light_brighten, light_darken, light_org))

        self.menus.file.aboutToShow.connect(self.update_file_menu)

        # Custom context menu for the canvas widget:
        add_actions(self.canvas.menus[0], self.actions.beginnerContext)
        add_actions(self.canvas.menus[1], (
            action('&Copy here', self.copy_shape),
            action('&Move here', self.move_shape)))

        self.tools = self.toolbar('Tools')
        self.actions.beginner = (
            open, open_dir, change_save_dir, open_next_image, open_prev_image, verify, save, save_format, None, create,
            copy, delete, None,
            zoom_in, zoom, zoom_out, fit_window, fit_width, None,
            light_brighten, light, light_darken, light_org)

        self.actions.advanced = (
            open, open_dir, change_save_dir, open_next_image, open_prev_image, save, save_format, None,
            create_mode, edit_mode, None,
            hide_all, show_all)

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.file_path = ustr(default_filename)
        self.last_open_dir = None
        self.recent_files = []
        self.max_recent = 7
        self.line_color = None
        self.fill_color = None
        self.zoom_level = 100
        self.fit_window = False
        # Add Chris
        self.difficult = False

        # Fix the compatible issue for qt4 and qt5. Convert the QStringList to python list
        if settings.get(SETTING_RECENT_FILES):
            if have_qstring():
                recent_file_qstring_list = settings.get(SETTING_RECENT_FILES)
                self.recent_files = [ustr(i) for i in recent_file_qstring_list]
            else:
                self.recent_files = recent_file_qstring_list = settings.get(SETTING_RECENT_FILES)

        size = settings.get(SETTING_WIN_SIZE, QSize(600, 500))
        position = QPoint(0, 0)
        saved_position = settings.get(SETTING_WIN_POSE, position)
        # Fix the multiple monitors issue
        for i in range(QApplication.desktop().screenCount()):
            if QApplication.desktop().availableGeometry(i).contains(saved_position):
                position = saved_position
                break
        self.resize(size)
        self.move(position)
        save_dir = ustr(settings.get(SETTING_SAVE_DIR, None))
        self.last_open_dir = ustr(settings.get(SETTING_LAST_OPEN_DIR, None))
        if self.default_save_dir is None and save_dir is not None and os.path.exists(save_dir):
            self.default_save_dir = save_dir
            self.statusBar().showMessage('%s started. Annotation will be saved to %s' %
                                         (__appname__, self.default_save_dir))
            self.statusBar().show()

        self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))
        Shape.line_color = self.line_color = QColor(settings.get(SETTING_LINE_COLOR, DEFAULT_LINE_COLOR))
        Shape.fill_color = self.fill_color = QColor(settings.get(SETTING_FILL_COLOR, DEFAULT_FILL_COLOR))
        self.canvas.set_drawing_color(self.line_color)
        # Add chris
        Shape.difficult = self.difficult

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        if xbool(settings.get(SETTING_ADVANCE_MODE, False)):
            self.actions.advancedMode.setChecked(True)
            self.toggle_advanced_mode()

        # Populate the File menu dynamically.
        self.update_file_menu()

        # Since loading the file may take some time, make sure it runs in the background.
        if self.file_path and os.path.isdir(self.file_path):
            self.queue_event(partial(self.import_dir_images, self.file_path or ""))
        elif self.file_path:
            self.queue_event(partial(self.load_file, self.file_path or ""))

        # Callbacks:
        self.zoom_widget.valueChanged.connect(self.paint_canvas)
        self.light_widget.valueChanged.connect(self.paint_canvas)

        self.populate_mode_actions()

        # Display cursor coordinates at the right of status bar
        self.label_coordinates = QLabel('')
        self.statusBar().addPermanentWidget(self.label_coordinates)

        # Open Dir if default file
        if self.file_path and os.path.isdir(self.file_path):
            self.open_dir_dialog(dir_path=self.file_path, silent=True)

    def extract_train_data_with_fog_threshold(self):
        # 如果当前self.file_path为空，则弹出警告框
        if not self.file_path:
            QMessageBox.warning(self, "Warning", "No image loaded.")
            return
        # 弹出保存框，选择输入文件夹路径
        input_folder = QFileDialog.getExistingDirectory(self, "选择包含images和labels文件夹路径", os.path.dirname(self.file_path))
        # 如果文件夹中没有images和labels文件夹，则弹出警告框
        if not os.path.exists(os.path.join(input_folder, 'images')) or not os.path.exists(os.path.join(input_folder, 'labels')):
            QMessageBox.warning(self, "Warning", "输入文件夹中没有images和labels文件夹。")
            return
        # 弹出保存框，选择保存路径，默认在当前文件所在文件夹
        save_dir = QFileDialog.getExistingDirectory(self, "选择保存训练数据位置", os.path.dirname(self.file_path))
        # 创建阈值有雾训练数据文件夹
        if not os.path.exists(os.path.join(save_dir, 'Thread_fog_train_data')):
            os.makedirs(os.path.join(save_dir, 'Thread_fog_train_data'))
        save_dir = os.path.join(save_dir, 'Thread_fog_train_data')
        if not save_dir:
            return
        image_folder = os.path.join(input_folder, 'images')
        label_folder = os.path.join(input_folder, 'labels')
        threshold = float(self.fog_threshold_edit.text())
        MainWindow.process_images(self, image_folder, label_folder, save_dir, threshold=threshold)
        # 弹出提示框
        QMessageBox.information(self, "Information", "提取阈值有雾训练数据完成。")


    def process_images(self, image_folder, label_folder, output_folder, threshold=0.0):
        """
        处理图像并提取雾检测结果。
        :param input_folder: 图像文件夹路径
        :param label_folder: TXT标签文件夹路径
        :param output_folder: 输出文件夹路径
        """
        os.makedirs(output_folder, exist_ok=True)

        # 遍历所有标签文件
        for label_file in os.listdir(label_folder):
            if label_file.lower().endswith('.txt'):
                ima_name = os.path.splitext(label_file)[0] + ".jpg"
                ima_path = os.path.join(image_folder, ima_name)
                if not os.path.exists(ima_path):
                    # 弹窗提示文件不存在
                    QMessageBox.warning(self, "Warning", f"文件不存在: {ima_path}")
                    # 跳过当前文件
                    continue
                # 读取图像
                image = cv2.imread(ima_path)# 避免中文路径报错
                if image is None:
                    # 弹窗提示无法读取图像
                    QMessageBox.warning(self, "Warning", f"无法读取图像: {ima_path}")
                    # 跳过当前文件
                    continue
                # 检查第一行第一个值是否为 0
                with open(os.path.join(label_folder, label_file), 'r') as original_txt:
                    lines = original_txt.readlines()
                    first_line = lines[0].strip().split()
                    if not first_line or first_line[0] != '0':
                        # 弹窗提示第一行第一个值不是 0
                        QMessageBox.warning(self, "Warning", f"跳过文件: {label_file}，第一行第一个值不是 0")
                        # 跳过当前文件
                        continue

                    # 读取TXT标签并转换为ROI
                    rois = MainWindow.read_txt_labels(os.path.join(label_folder, label_file), image.shape[:2])
                    if not rois:
                        # 弹窗提示未找到ROI区域
                        QMessageBox.warning(self, "Warning", f"未找到ROI区域: {label_file}")
                        # 跳过当前文件
                        continue
                    # 创建输出路径
                    output_txt_path = os.path.join(output_folder, 'labels')
                    output_image_path = os.path.join(output_folder, 'images')
                    if not os.path.exists(output_txt_path):
                        os.makedirs(output_txt_path)
                    if not os.path.exists(output_image_path):
                        os.makedirs(output_image_path)

                    # 用于存储符合条件的行
                    filtered_lines = []

                    # 遍历所有ROI区域
                    for idx, roi in enumerate(rois):
                        is_fog, ratio = MainWindow.detect_fog(image, roi, threshold)
                        if is_fog:
                            # 保存符合条件的ROI区域
                            filtered_lines.append(lines[idx])

                    # 如果有符合条件的行，则写入到新的txt文件中，并保存对应的图像
                    if filtered_lines:
                        # 写入新的txt文件
                        with open(os.path.join(output_txt_path, label_file), 'w') as new_txt:
                            for line in filtered_lines:
                                new_txt.write(line)
                        # 保存对应的图像
                        cv2.imwrite(os.path.join(output_image_path, ima_name), image)
                    else:
                        # 输出没有符合条件的ROI
                        print(f"没有符合条件的ROI: {label_file}")
                        # 跳过当前文件
                        continue

    @staticmethod
    def read_txt_labels(txt_path, image_shape):
        """
        读取TXT标签文件，解析ROI区域。
        :param txt_path: TXT文件路径
        :param image_shape: 图像的形状 (height, width)
        :return: ROI区域列表 [(x, y, w, h)]
        """
        rois = []
        with open(txt_path, 'r') as file:
            for line in file.readlines():
                values = line.strip().split()
                if len(values) == 5:
                    # 解析归一化坐标
                    _, x_center, y_center, width, height = map(float, values)
                    # 转换为像素坐标
                    x = int((x_center - width / 2) * image_shape[1])
                    y = int((y_center - height / 2) * image_shape[0])
                    w = int(width * image_shape[1])
                    h = int(height * image_shape[0])
                    rois.append((x, y, w, h))
        return rois
    def extract_train_data(self):
        # 如果当前self.file_path为空，则弹出警告框
        if not self.file_path:
            QMessageBox.warning(self, "Warning", "No image loaded.")
            return
        # 弹出保存框，选择保存路径，默认在当前文件所在文件夹
        save_dir = QFileDialog.getExistingDirectory(self, "选择保存训练数据位置", os.path.dirname(self.file_path))
        # 创建标签有雾训练数据文件夹
        if not os.path.exists(os.path.join(save_dir, 'Label_fog_train_data')):
            os.makedirs(os.path.join(save_dir, 'Label_fog_train_data'))
        save_dir = os.path.join(save_dir, 'Label_fog_train_data')
        if not save_dir:
            return
        # 获取所有txt文件
        dir_path = os.path.dirname(self.file_path)
        txt_files = [os.path.join(dir_path, file) for file in os.listdir(dir_path) if file.endswith('.txt')]
        # 创建labels和images文件夹
        if not os.path.exists(os.path.join(save_dir, 'labels')):
            os.makedirs(os.path.join(save_dir, 'labels'))
        if not os.path.exists(os.path.join(save_dir, 'images')):
            os.makedirs(os.path.join(save_dir, 'images'))
        # 读取所有txt文件，除了名为classes.txt的文件
        for file in txt_files:
            if os.path.basename(file) == 'classes.txt':
                continue
            with open(file, 'r', encoding='utf-8') as f:
                # 如果该txt文件第一行第一个字符为0，则移动到保存路径下的labels文件夹，没有labels和images文件夹则创建
                first_line = f.readline().strip()
                if first_line and first_line.split() and first_line.split()[0] == '0':
                    # 复制txt文件到保存路径下的labels文件夹
                    shutil.copy(file, os.path.join(save_dir, 'labels'))
                    # 复制对应的图片文件到保存路径下的images文件夹
                    image_file = os.path.join(dir_path, os.path.splitext(os.path.basename(file))[0] + '.jpg')
                    if os.path.exists(image_file):
                        shutil.copy(image_file, os.path.join(save_dir, 'images'))
                    else:
                        # 弹出提示框
                        QMessageBox.warning(self, "Warning", "Corresponding image file not found.")
                        return

        # 弹出提示框
        QMessageBox.information(self, "Extract Train Data", "Train data has been extracted successfully.")

    def extract_class0_labels(self):
        """提取类别ID为0的标签文件，不进行V/S比计算"""
        # 如果当前self.file_path为空，则弹出警告框
        if not self.file_path:
            QMessageBox.warning(self, "Warning", "No image loaded.")
            return
        
        # 弹出保存框，选择保存路径，默认在当前文件所在文件夹
        save_dir = QFileDialog.getExistingDirectory(self, "选择保存类别0标签文件位置", os.path.dirname(self.file_path))
        if not save_dir:
            return
        
        # 获取当前目录名称
        current_dir_name = os.path.basename(self.dir_name) if self.dir_name else 'unknown'
        
        # 创建类别0标签数据文件夹，名称与当前目录一致
        class0_folder = os.path.join(save_dir, current_dir_name)
        if not os.path.exists(class0_folder):
            os.makedirs(class0_folder)
        
        # 直接使用当前目录命名的文件夹，不创建子文件夹
        
        # 获取所有txt文件
        dir_path = os.path.dirname(self.file_path)
        txt_files = [os.path.join(dir_path, file) for file in os.listdir(dir_path) if file.endswith('.txt')]
        
        # 处理classes.txt文件
        classes_file = os.path.join(dir_path, 'classes.txt')
        target_classes_file = os.path.join(class0_folder, 'classes.txt')
        
        if os.path.exists(classes_file):
            # 如果存在classes.txt，直接复制
            shutil.copy(classes_file, class0_folder)
        else:
            # 如果不存在classes.txt，创建一个包含标签的classes.txt
            # 从标签文件中收集所有唯一的标签
            unique_labels = set()
            for file in txt_files:
                if os.path.basename(file) == 'classes.txt':
                    continue
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                parts = line.split()
                                if parts:
                                    class_id = parts[0]
                                    # 尝试从现有的标签历史中获取标签名称
                                    if hasattr(self, 'label_hist') and self.label_hist:
                                        try:
                                            class_index = int(class_id)
                                            if 0 <= class_index < len(self.label_hist):
                                                unique_labels.add(self.label_hist[class_index])
                                            else:
                                                unique_labels.add(f'class_{class_id}')
                                        except (ValueError, IndexError):
                                            unique_labels.add(f'class_{class_id}')
                                    else:
                                        # 如果没有标签历史，使用默认命名
                                        unique_labels.add(f'class_{class_id}')
                except Exception as e:
                    continue
            
            # 创建classes.txt文件
            if unique_labels:
                with open(target_classes_file, 'w', encoding='utf-8') as f:
                    for label in sorted(unique_labels):
                        f.write(f"{label}\n")
        
        # 统计信息
        total_files = 0
        class0_files = 0
        copied_images = 0
        
        # 读取所有txt文件，除了名为classes.txt的文件
        for file in txt_files:
            if os.path.basename(file) == 'classes.txt':
                continue
            
            total_files += 1
            
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if first_line and first_line.split():
                        first_value = first_line.split()[0]
                        # 如果该txt文件第一行第一个字符为0，则复制
                        if first_value == '0':
                            class0_files += 1
                            
                            # 复制txt文件到目标文件夹
                            shutil.copy(file, class0_folder)
                            
                            # 复制对应的图片文件到目标文件夹
                            image_file = os.path.join(dir_path, os.path.splitext(os.path.basename(file))[0] + '.jpg')
                            if os.path.exists(image_file):
                                shutil.copy(image_file, class0_folder)
                                copied_images += 1
                            else:
                                # 尝试其他图像格式
                                for ext in ['.png', '.jpeg', '.bmp', '.tiff', '.tif']:
                                    alt_image_file = os.path.join(dir_path, os.path.splitext(os.path.basename(file))[0] + ext)
                                    if os.path.exists(alt_image_file):
                                        shutil.copy(alt_image_file, class0_folder)
                                        copied_images += 1
                                        break
                                else:
                                    print(f"警告：未找到对应的图像文件: {os.path.basename(file)}")
            except Exception as e:
                print(f"处理文件 {file} 时出错: {e}")
                continue
        
        # 显示结果
        result_msg = f"提取完成！\n\n"
        result_msg += f"总标签文件数: {total_files}\n"
        result_msg += f"类别0文件数: {class0_files}\n"
        result_msg += f"成功复制图像数: {copied_images}\n"
        classes_status = "已复制" if os.path.exists(classes_file) else "已创建"
        result_msg += f"classes.txt状态: {classes_status}\n"
        result_msg += f"保存位置: {class0_folder}"
        
        QMessageBox.information(self, "提取类别0标签完成", result_msg)

    def generate_video_label(self):
        # 如果当前self.file_path为空，则弹出警告框
        if not self.file_path:
            QMessageBox.warning(self, "Warning", "No image loaded.")
            return
        # 获取当前文件夹路径
        dir_path = os.path.dirname(self.file_path)
        # 统计文件夹中含有图片数量
        image_files = [os.path.join(dir_path, file) for file in os.listdir(dir_path) if file.endswith('.jpg')]
        # 视频帧数
        frame_num = len(image_files)
        # 设置一个储存视频标签的变量
        video_labels = []
        # 按照视频帧数填充视频标签
        for i in range(frame_num):
            video_labels.append(f"{i}-{i} 4 0")
        # 获取当前文件夹下所有的txt文件
        txt_files = [os.path.join(dir_path, file) for file in os.listdir(dir_path) if file.endswith('.txt')]
        # 删除文件夹中的空txt文件
        for file in txt_files:
            if os.path.getsize(file) == 0:
                os.remove(file)
        # 再次获取当前文件夹下所有的txt文件
        txt_files = [os.path.join(dir_path, file) for file in os.listdir(dir_path) if file.endswith('.txt')]
        # 获取txt文件中的类别，并且将视频标签与类别对应
        # 循环所有txt文件
        for file in txt_files:
            # 读取txt文件
            # 如果txt文件名为classses.txt，则跳过
            if os.path.basename(file) == 'classes.txt':
                # 储存标签中数字对应的类别名称
                with open(file, 'r', encoding='utf-8') as f:
                    # 将文件内容按照换行符分割
                    lines = f.readlines()
                    # 储存为一个字符串
                    classes_str = ''.join(lines)
                    # 按照换行符分割字符串
                    classes = classes_str.split('\n')
                continue
            with open(file, 'r', encoding='utf-8') as f:
                # 根据文件名获取视频帧号(后缀前面的数字)
                # 例如：fog-T01S01I01L0202H700BTctotalLtotal_video_1_20250102_125143_ori_2.txt
                # 则获取的视频帧号为_2.txt中的2
                frame = int(os.path.splitext(os.path.basename(file))[0].split('_')[-1])
                lines = f.readlines()
                # 读取第一行
                if lines and lines[0].strip() and lines[0].strip().split():
                    label = int(lines[0].strip().split()[0])
                else:
                    continue
                if classes[label] == 'fog':
                    label_name = '5'
                elif classes[label] == '999':
                    label_name = '999'
                # 填充视频标签
                video_labels[int(frame - 1)] = f"{frame - 1}-{frame - 1} {label_name} 0"

        # 写入视频标签文件
        # 视频标签文件名按照文件夹的名称命名
        # 可以自行选择储存位置
        save_dir = os.path.join(dir_path, 'video_labels')
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        video_label_file = os.path.join(save_dir, os.path.basename(dir_path) + '.txt')
        with open(video_label_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(video_labels))
        # 弹出提示框
        QMessageBox.information(self, "Generate Video Label", "Video label file has been generated successfully.")

    def generate_video_label_with_fog_threshold(self):
        # 如果当前self.file_path为空，则弹出警告框
        if not self.file_path:
            QMessageBox.warning(self, "Warning", "No image loaded.")
            return
        # 获取当前文件夹路径
        dir_path = os.path.dirname(self.file_path)
        # 统计文件夹中含有图片数量
        image_files = [os.path.join(dir_path, file) for file in os.listdir(dir_path) if file.endswith('.jpg')]
        # 视频帧数
        frame_num = len(image_files)
        # 设置一个储存视频标签的变量
        video_labels = []
        # 按照视频帧数填充视频标签
        for i in range(frame_num):
            video_labels.append(f"{i}-{i} 4 0")
        # 获取当前文件夹下所有的txt文件
        txt_files = [os.path.join(dir_path, file) for file in os.listdir(dir_path) if file.endswith('.txt')]
        # 删除文件夹中的空txt文件
        for file in txt_files:
            if os.path.getsize(file) == 0:
                os.remove(file)
        # 再次获取当前文件夹下所有的txt文件
        txt_files = [os.path.join(dir_path, file) for file in os.listdir(dir_path) if file.endswith('.txt')]
        # 获取txt文件中的类别，并且将视频标签与类别对应
        # 循环所有txt文件
        for file in txt_files:
            # 读取txt文件
            # 如果txt文件名为classses.txt，则跳过
            if os.path.basename(file) == 'classes.txt':
                continue
            with open(file, 'r', encoding='utf-8') as f:
                # 根据文件名获取视频帧号(后缀前面的数字)
                # 例如：fog-T01S01I01L0202H700BTctotalLtotal_video_1_20250102_125143_ori_2.txt
                # 则获取的视频帧号为_2.txt中的2
                frame = int(os.path.splitext(os.path.basename(file))[0].split('_')[-1])
                # label = f.readline().strip().split()[0]
                lines = f.readlines()
                if lines and lines[0].strip() and lines[0].strip().split():
                    label = lines[0].strip().split()[0]
                else:
                    continue
                # 标签为999的情况
                if label == '1':
                    video_labels[int(frame - 1)] = f"{frame - 1}-{frame - 1} 999 0"
                    continue
                elif label == '0':# 标签为有雾的情况
                    # 读取标签文件对应的图像
                    image_file = os.path.join(dir_path, os.path.splitext(os.path.basename(file))[0] + '.jpg')
                    if not os.path.exists(image_file):
                        # 弹出提示框
                        QMessageBox.warning(self, "Warning", "Corresponding image file not found.")
                        return
                    # 获取图像的image_shape
                    image = cv2.imread(image_file)
                    if image is None:
                        # 弹出提示框
                        QMessageBox.warning(self, "Warning", f"无法读取图像: {image_file}")
                        return
                    image_shape = image.shape[:2]
                    rois = []  # 储存标签中的标注框
                    # 用于判断是否是有雾标签的条件
                    is_fog_label = False
                    for line in lines:
                        values = line.strip().split()
                        if len(values) == 5 and values[0] == '0':  # 标签为有雾
                            # 解析归一化坐标
                            _, x_center, y_center, width, height = map(float, values)
                            # 转换为像素坐标
                            x = int((x_center - width / 2) * image_shape[1])
                            y = int((y_center - height / 2) * image_shape[0])
                            w = int(width * image_shape[1])
                            h = int(height * image_shape[0])
                            rois.append((x, y, w, h))
                    # 获取判断有雾阈值
                    if not self.fog_threshold_edit:
                        # 弹出提示框
                        QMessageBox.warning(self, "Warning", "Please input the fog threshold.")
                        return
                    threshold = float(self.fog_threshold_edit.text())
                    # 判断是否有雾
                    for idx, roi in enumerate(rois):
                        is_fog, ratio = self.detect_fog(image, roi, threshold)
                        if is_fog:
                            is_fog_label = True
                            break
                    # 标签为有雾的情况
                    if is_fog_label:
                        video_labels[int(frame - 1)] = f"{frame - 1}-{frame - 1} 5 0"
                    else:
                        video_labels[int(frame - 1)] = f"{frame - 1}-{frame - 1} 4 0"

        # 写入视频标签文件
        # 视频标签文件名按照文件夹的名称命名
        # 可以自行选择储存位置
        save_dir = os.path.join(dir_path, 'thread_video_labels')
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        video_label_file = os.path.join(save_dir, os.path.basename(dir_path) + '.txt')
        with open(video_label_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(video_labels))
        # 弹出提示框
        QMessageBox.information(self, "Generate Video Label",
                                "Video label file has been generated successfully.")

    @staticmethod
    def detect_fog(image, roi, threshold):
        """
        检测图像中是否存在雾。
        :param image: 输入图像（BGR格式）
        :param roi: 感兴趣区域（ROI）的坐标 [x, y, width, height]
        :param threshold: V/S比值的阈值
        :return: 是否存在雾，V/S比值
        """
        x, y, w, h = roi
        roi_image = image[y:y + h, x:x + w]

        if roi_image.size == 0:
            return False, 0.0

        hsv_image = cv2.cvtColor(roi_image, cv2.COLOR_BGR2HSV)
        s = hsv_image[:, :, 1].astype(np.float32)  # 饱和度
        v = hsv_image[:, :, 2].astype(np.float32)  # 亮度

        with np.errstate(divide='ignore', invalid='ignore'):
            ratio = np.nanmean(v / s)  # 忽略NaN值
            ratio = ratio * 10

        return ratio > threshold, ratio

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.canvas.set_drawing_shape_to_square(False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            # Draw rectangle if Ctrl is pressed
            self.canvas.set_drawing_shape_to_square(True)
        # Ctrl+A 快捷键：全选所有检测框
        elif event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_A:
            self.select_all_shapes()

    # Support Functions #
    def set_format(self, save_format):
        if save_format == FORMAT_PASCALVOC:
            self.actions.save_format.setText(FORMAT_PASCALVOC)
            self.actions.save_format.setIcon(new_icon("format_voc"))
            self.label_file_format = LabelFileFormat.PASCAL_VOC
            LabelFile.suffix = XML_EXT

        elif save_format == FORMAT_YOLO:
            self.actions.save_format.setText(FORMAT_YOLO)
            self.actions.save_format.setIcon(new_icon("format_yolo"))
            self.label_file_format = LabelFileFormat.YOLO
            LabelFile.suffix = TXT_EXT

        elif save_format == FORMAT_CREATEML:
            self.actions.save_format.setText(FORMAT_CREATEML)
            self.actions.save_format.setIcon(new_icon("format_createml"))
            self.label_file_format = LabelFileFormat.CREATE_ML
            LabelFile.suffix = JSON_EXT

    def change_format(self):
        if self.label_file_format == LabelFileFormat.PASCAL_VOC:
            self.set_format(FORMAT_YOLO)
        elif self.label_file_format == LabelFileFormat.YOLO:
            self.set_format(FORMAT_CREATEML)
        elif self.label_file_format == LabelFileFormat.CREATE_ML:
            self.set_format(FORMAT_PASCALVOC)
        else:
            raise ValueError('Unknown label file format.')
        self.set_dirty()

    def no_shapes(self):
        return not self.items_to_shapes

    def toggle_advanced_mode(self, value=True):
        self._beginner = not value
        self.canvas.set_editing(True)
        self.populate_mode_actions()
        self.edit_button.setVisible(not value)
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            self.dock.setFeatures(self.dock.features() | self.dock_features)
        else:
            self.dock.setFeatures(self.dock.features() ^ self.dock_features)

    def populate_mode_actions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        add_actions(self.tools, tool)
        self.canvas.menus[0].clear()
        add_actions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create,) if self.beginner() \
            else (self.actions.createMode, self.actions.editMode)
        add_actions(self.menus.edit, actions + self.actions.editMenu)

    def set_beginner(self):
        self.tools.clear()
        add_actions(self.tools, self.actions.beginner)

    def set_advanced(self):
        self.tools.clear()
        add_actions(self.tools, self.actions.advanced)

    def set_dirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def set_clean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)

    def toggle_actions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for z in self.actions.lightActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queue_event(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def reset_state(self):
        self.items_to_shapes.clear()
        self.shapes_to_items.clear()
        self.label_list.clear()
        self.file_path = None
        self.image_data = None
        self.label_file = None
        self.canvas.reset_state()
        self.label_coordinates.clear()
        self.combo_box.cb.clear()

    def current_item(self):
        items = self.label_list.selectedItems()
        if items:
            return items[0]
        return None

    def add_recent_file(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        elif len(self.recent_files) >= self.max_recent:
            self.recent_files.pop()
        self.recent_files.insert(0, file_path)

    def beginner(self):
        return self._beginner

    def advanced(self):
        return not self.beginner()

    def show_tutorial_dialog(self, browser='default', link=None):
        if link is None:
            link = self.screencast

        if browser.lower() == 'default':
            wb.open(link, new=2)
        elif browser.lower() == 'chrome' and self.os_name == 'Windows':
            if shutil.which(browser.lower()):  # 'chrome' not in wb._browsers in windows
                wb.register('chrome', None, wb.BackgroundBrowser('chrome'))
            else:
                chrome_path = "D:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
                if os.path.isfile(chrome_path):
                    wb.register('chrome', None, wb.BackgroundBrowser(chrome_path))
            try:
                wb.get('chrome').open(link, new=2)
            except:
                wb.open(link, new=2)
        elif browser.lower() in wb._browsers:
            wb.get(browser.lower()).open(link, new=2)

    def show_default_tutorial_dialog(self):
        self.show_tutorial_dialog(browser='default')

    def show_info_dialog(self):
        from libs.__init__ import __version__
        msg = u'Name:{0} \nApp Version:{1} \n{2} '.format(__appname__, __version__, sys.version_info)
        QMessageBox.information(self, u'Information', msg)

    def show_shortcuts_dialog(self):
        self.show_tutorial_dialog(browser='default', link='https://github.com/tzutalin/labelImg#Hotkeys')

    def create_shape(self):
        assert self.beginner()
        self.canvas.set_editing(False)
        self.actions.create.setEnabled(False)

    def toggle_drawing_sensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        self.actions.editMode.setEnabled(not drawing)
        if not drawing and self.beginner():
            # Cancel creation.
            print('Cancel creation.')
            self.canvas.set_editing(True)
            self.canvas.restore_cursor()
            self.actions.create.setEnabled(True)

    def toggle_draw_mode(self, edit=True):
        self.canvas.set_editing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)

    def set_create_mode(self):
        assert self.advanced()
        self.toggle_draw_mode(False)

    def set_edit_mode(self):
        assert self.advanced()
        self.toggle_draw_mode(True)
        self.label_selection_changed()

    def update_file_menu(self):
        curr_file_path = self.file_path

        def exists(filename):
            return os.path.exists(filename)

        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recent_files if f !=
                 curr_file_path and exists(f)]
        for i, f in enumerate(files):
            icon = new_icon('labels')
            action = QAction(
                icon, '&%d %s' % (i + 1, QFileInfo(f).fileName()), self)
            action.triggered.connect(partial(self.load_recent, f))
            menu.addAction(action)

    def pop_label_list_menu(self, point):
        self.menus.labelList.exec_(self.label_list.mapToGlobal(point))

    def edit_label(self):
        if not self.canvas.editing():
            return
        item = self.current_item()
        if not item:
            return
        text = self.label_dialog.pop_up(item.text())
        if text is not None:
            item.setText(text)
            item.setBackground(generate_color_by_text(text))
            self.set_dirty()
            self.update_combo_box()

    # Tzutalin 20160906 : Add file list and dock to move faster
    def file_item_double_clicked(self, item=None):
        self.cur_img_idx = self.m_img_list.index(ustr(item.text()))
        filename = self.m_img_list[self.cur_img_idx]
        if filename:
            self.load_file(filename)

    # Add chris
    def button_state(self, item=None):
        """ Function to handle difficult examples
        Update on each object """
        if not self.canvas.editing():
            return

        item = self.current_item()
        if not item:  # If not selected Item, take the first one
            item = self.label_list.item(self.label_list.count() - 1)

        difficult = self.diffc_button.isChecked()

        try:
            shape = self.items_to_shapes[item]
        except:
            pass
        # Checked and Update
        try:
            if difficult != shape.difficult:
                shape.difficult = difficult
                self.set_dirty()
            else:  # User probably changed item visibility
                self.canvas.set_shape_visible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    # React to canvas signals.
    def shape_selection_changed(self, selected=False):
        if self._no_selection_slot:
            self._no_selection_slot = False
        else:
            shape = self.canvas.selected_shape
            if shape:
                self.shapes_to_items[shape].setSelected(True)
            else:
                self.label_list.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)
        # 启用/禁用复制检测框按钮
        self.copy_bbox_to_others_button.setEnabled(selected)
        # 随机复制按钮只需要有目录即可，不需要选择检测框
        self.copy_all_bbox_randomly_button.setEnabled(bool(self.dir_name))

    def add_label(self, shape):
        shape.paint_label = self.display_label_option.isChecked()
        item = HashableQListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setBackground(generate_color_by_text(shape.label))
        self.items_to_shapes[item] = shape
        self.shapes_to_items[shape] = item
        self.label_list.addItem(item)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)
        self.update_combo_box()

    def remove_label(self, shape):
        if shape is None:
            # print('rm empty label')
            return
        item = self.shapes_to_items[shape]
        self.label_list.takeItem(self.label_list.row(item))
        del self.shapes_to_items[shape]
        del self.items_to_shapes[item]
        self.update_combo_box()

    def load_labels(self, shapes):
        s = []
        for label, points, line_color, fill_color, difficult in shapes:
            shape = Shape(label=label)
            for x, y in points:

                # Ensure the labels are within the bounds of the image. If not, fix them.
                x, y, snapped = self.canvas.snap_point_to_canvas(x, y)
                if snapped:
                    self.set_dirty()

                shape.add_point(QPointF(x, y))
            shape.difficult = difficult
            shape.close()
            s.append(shape)

            if line_color:
                shape.line_color = QColor(*line_color)
            else:
                shape.line_color = generate_color_by_text(label)

            if fill_color:
                shape.fill_color = QColor(*fill_color)
            else:
                shape.fill_color = generate_color_by_text(label)

            self.add_label(shape)
        self.update_combo_box()
        self.canvas.load_shapes(s)

    def update_combo_box(self):
        # Get the unique labels and add them to the Combobox.
        items_text_list = [str(self.label_list.item(i).text()) for i in range(self.label_list.count())]

        unique_text_list = list(set(items_text_list))
        # Add a null row for showing all the labels
        unique_text_list.append("")
        unique_text_list.sort()

        self.combo_box.update_items(unique_text_list)

    def save_labels(self, annotation_file_path):
        annotation_file_path = ustr(annotation_file_path)
        if self.label_file is None:
            self.label_file = LabelFile()
            self.label_file.verified = self.canvas.verified

        def format_shape(s):
            return dict(label=s.label,
                        line_color=s.line_color.getRgb(),
                        fill_color=s.fill_color.getRgb(),
                        points=[(p.x(), p.y()) for p in s.points],
                        # add chris
                        difficult=s.difficult)

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        # Can add different annotation formats here
        try:
            if self.label_file_format == LabelFileFormat.PASCAL_VOC:
                if annotation_file_path[-4:].lower() != ".xml":
                    annotation_file_path += XML_EXT
                self.label_file.save_pascal_voc_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                       self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.YOLO:
                if annotation_file_path[-4:].lower() != ".txt":
                    annotation_file_path += TXT_EXT
                self.label_file.save_yolo_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                 self.label_hist,
                                                 self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.CREATE_ML:
                if annotation_file_path[-5:].lower() != ".json":
                    annotation_file_path += JSON_EXT
                self.label_file.save_create_ml_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                      self.label_hist, self.line_color.getRgb(),
                                                      self.fill_color.getRgb())
            else:
                self.label_file.save(annotation_file_path, shapes, self.file_path, self.image_data,
                                     self.line_color.getRgb(), self.fill_color.getRgb())
            print('Image:{0} -> Annotation:{1}'.format(self.file_path, annotation_file_path))
            return True
        except LabelFileError as e:
            self.error_message(u'Error saving label data', u'<b>%s</b>' % e)
            return False

    def copy_selected_shape(self):
        self.add_label(self.canvas.copy_selected_shape())
        # fix copy and delete
        self.shape_selection_changed(True)

    def combo_selection_changed(self, index):
        text = self.combo_box.cb.itemText(index)
        for i in range(self.label_list.count()):
            if text == "":
                self.label_list.item(i).setCheckState(2)
            elif text != self.label_list.item(i).text():
                self.label_list.item(i).setCheckState(0)
            else:
                self.label_list.item(i).setCheckState(2)

    def default_label_combo_selection_changed(self, index):
        self.default_label = self.label_hist[index]

    def label_selection_changed(self):
        item = self.current_item()
        if item and self.canvas.editing():
            self._no_selection_slot = True
            self.canvas.select_shape(self.items_to_shapes[item])
            shape = self.items_to_shapes[item]
            # Add Chris
            self.diffc_button.setChecked(shape.difficult)

    def label_item_changed(self, item):
        shape = self.items_to_shapes[item]
        label = item.text()
        if label != shape.label:
            shape.label = item.text()
            shape.line_color = generate_color_by_text(shape.label)
            self.set_dirty()
        else:  # User probably changed item visibility
            self.canvas.set_shape_visible(shape, item.checkState() == Qt.Checked)

    # Callback functions:
    def new_shape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        if not self.use_default_label_checkbox.isChecked():
            if len(self.label_hist) > 0:
                self.label_dialog = LabelDialog(
                    parent=self, list_item=self.label_hist)

            # Sync single class mode from PR#106
            if self.single_class_mode.isChecked() and self.lastLabel:
                text = self.lastLabel
            else:
                text = self.label_dialog.pop_up(text=self.prev_label_text)
                self.lastLabel = text
        else:
            text = self.default_label

        # Add Chris
        self.diffc_button.setChecked(False)
        if text is not None:
            self.prev_label_text = text
            generate_color = generate_color_by_text(text)
            shape = self.canvas.set_last_label(text, generate_color, generate_color)
            self.add_label(shape)
            if self.beginner():  # Switch to edit mode.
                self.canvas.set_editing(True)
                self.actions.create.setEnabled(True)
            else:
                self.actions.editMode.setEnabled(True)
            self.set_dirty()

            if text not in self.label_hist:
                self.label_hist.append(text)
        else:
            # self.canvas.undoLastLine()
            self.canvas.reset_all_lines()

    def scroll_request(self, delta, orientation):
        units = - delta / (8 * 15)
        bar = self.scroll_bars[orientation]
        bar.setValue(int(bar.value() + bar.singleStep() * units))

    def set_zoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoom_mode = self.MANUAL_ZOOM
        # Arithmetic on scaling factor often results in float
        # Convert to int to avoid type errors
        self.zoom_widget.setValue(int(value))

    def add_zoom(self, increment=10):
        self.set_zoom(self.zoom_widget.value() + increment)

    def zoom_request(self, delta):
        # get the current scrollbar positions
        # calculate the percentages ~ coordinates
        h_bar = self.scroll_bars[Qt.Horizontal]
        v_bar = self.scroll_bars[Qt.Vertical]

        # get the current maximum, to know the difference after zooming
        h_bar_max = h_bar.maximum()
        v_bar_max = v_bar.maximum()

        # get the cursor position and canvas size
        # calculate the desired movement from 0 to 1
        # where 0 = move left
        #       1 = move right
        # up and down analogous
        cursor = QCursor()
        pos = cursor.pos()
        relative_pos = QWidget.mapFromGlobal(self, pos)

        cursor_x = relative_pos.x()
        cursor_y = relative_pos.y()

        w = self.scroll_area.width()
        h = self.scroll_area.height()

        # the scaling from 0 to 1 has some padding
        # you don't have to hit the very leftmost pixel for a maximum-left movement
        margin = 0.1
        move_x = (cursor_x - margin * w) / (w - 2 * margin * w)
        move_y = (cursor_y - margin * h) / (h - 2 * margin * h)

        # clamp the values from 0 to 1
        move_x = min(max(move_x, 0), 1)
        move_y = min(max(move_y, 0), 1)

        # zoom in
        units = delta // (8 * 15)
        scale = 10
        self.add_zoom(scale * units)

        # get the difference in scrollbar values
        # this is how far we can move
        d_h_bar_max = h_bar.maximum() - h_bar_max
        d_v_bar_max = v_bar.maximum() - v_bar_max

        # get the new scrollbar values
        new_h_bar_value = int(h_bar.value() + move_x * d_h_bar_max)
        new_v_bar_value = int(v_bar.value() + move_y * d_v_bar_max)

        h_bar.setValue(new_h_bar_value)
        v_bar.setValue(new_v_bar_value)

    def light_request(self, delta):
        self.add_light(5 * delta // (8 * 15))

    def set_fit_window(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoom_mode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def set_fit_width(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoom_mode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def set_light(self, value):
        self.actions.lightOrg.setChecked(int(value) == 50)
        # Arithmetic on scaling factor often results in float
        # Convert to int to avoid type errors
        self.light_widget.setValue(int(value))

    def add_light(self, increment=10):
        self.set_light(self.light_widget.value() + increment)

    def toggle_polygons(self, value):
        for item, shape in self.items_to_shapes.items():
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def load_file(self, file_path=None):
        """Load the specified file, or the last opened file if None."""
        self.reset_state()
        self.canvas.setEnabled(False)
        if file_path is None:
            file_path = self.settings.get(SETTING_FILENAME)
        # Make sure that filePath is a regular python string, rather than QString
        file_path = ustr(file_path)

        # Fix bug: An  index error after select a directory when open a new file.
        unicode_file_path = ustr(file_path)
        unicode_file_path = os.path.abspath(unicode_file_path)
        # Tzutalin 20160906 : Add file list and dock to move faster
        # Highlight the file item
        if unicode_file_path and self.file_list_widget.count() > 0:
            if unicode_file_path in self.m_img_list:
                index = self.m_img_list.index(unicode_file_path)
                file_widget_item = self.file_list_widget.item(index)
                file_widget_item.setSelected(True)
            else:
                self.file_list_widget.clear()
                self.m_img_list.clear()

        if unicode_file_path and os.path.exists(unicode_file_path):
            if LabelFile.is_label_file(unicode_file_path):
                try:
                    self.label_file = LabelFile(unicode_file_path)
                except LabelFileError as e:
                    self.error_message(u'Error opening file',
                                       (u"<p><b>%s</b></p>"
                                        u"<p>Make sure <i>%s</i> is a valid label file.")
                                       % (e, unicode_file_path))
                    self.status("Error reading %s" % unicode_file_path)

                    return False
                self.image_data = self.label_file.image_data
                self.line_color = QColor(*self.label_file.lineColor)
                self.fill_color = QColor(*self.label_file.fillColor)
                self.canvas.verified = self.label_file.verified
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.image_data = read(unicode_file_path, None)
                self.label_file = None
                self.canvas.verified = False

            if isinstance(self.image_data, QImage):
                image = self.image_data
            else:
                image = QImage.fromData(self.image_data)
            if image.isNull():
                self.error_message(u'Error opening file',
                                   u"<p>Make sure <i>%s</i> is a valid image file." % unicode_file_path)
                self.status("Error reading %s" % unicode_file_path)
                return False
            self.status("Loaded %s" % os.path.basename(unicode_file_path))
            self.image = image
            self.file_path = unicode_file_path
            self.canvas.load_pixmap(QPixmap.fromImage(image))
            if self.label_file:
                self.load_labels(self.label_file.shapes)
            self.set_clean()
            self.canvas.setEnabled(True)
            self.adjust_scale(initial=True)
            self.paint_canvas()
            self.add_recent_file(self.file_path)
            self.toggle_actions(True)
            self.show_bounding_box_from_annotation_file(self.file_path)

            counter = self.counter_str()
            self.setWindowTitle(__appname__ + ' ' + file_path + ' ' + counter)

            # Default : select last item if there is at least one item
            if self.label_list.count():
                self.label_list.setCurrentItem(self.label_list.item(self.label_list.count() - 1))
                self.label_list.item(self.label_list.count() - 1).setSelected(True)

            self.canvas.setFocus(True)
            return True
        return False

    def counter_str(self):
        """
        Converts image counter to string representation.
        """
        return '[{} / {}]'.format(self.cur_img_idx + 1, self.img_count)

    def show_bounding_box_from_annotation_file(self, file_path):
        if self.default_save_dir is not None:
            basename = os.path.basename(os.path.splitext(file_path)[0])
            xml_path = os.path.join(self.default_save_dir, basename + XML_EXT)
            txt_path = os.path.join(self.default_save_dir, basename + TXT_EXT)
            json_path = os.path.join(self.default_save_dir, basename + JSON_EXT)

            """Annotation file priority:
            PascalXML > YOLO
            """
            if os.path.isfile(xml_path):
                self.load_pascal_xml_by_filename(xml_path)
            elif os.path.isfile(txt_path):
                self.load_yolo_txt_by_filename(txt_path)
            elif os.path.isfile(json_path):
                self.load_create_ml_json_by_filename(json_path, file_path)

        else:
            xml_path = os.path.splitext(file_path)[0] + XML_EXT
            txt_path = os.path.splitext(file_path)[0] + TXT_EXT
            json_path = os.path.splitext(file_path)[0] + JSON_EXT

            if os.path.isfile(xml_path):
                self.load_pascal_xml_by_filename(xml_path)
            elif os.path.isfile(txt_path):
                self.load_yolo_txt_by_filename(txt_path)
            elif os.path.isfile(json_path):
                self.load_create_ml_json_by_filename(json_path, file_path)

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull() \
                and self.zoom_mode != self.MANUAL_ZOOM:
            self.adjust_scale()
        super(MainWindow, self).resizeEvent(event)

    def paint_canvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoom_widget.value()
        self.canvas.overlay_color = self.light_widget.color()
        self.canvas.label_font_size = int(0.02 * max(self.image.width(), self.image.height()))
        self.canvas.adjustSize()
        self.canvas.update()

    def adjust_scale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoom_mode]()
        self.zoom_widget.setValue(int(100 * value))

    def scale_fit_window(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scale_fit_width(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.may_continue():
            event.ignore()
        settings = self.settings
        # If it loads images from dir, don't load it at the beginning
        if self.dir_name is None:
            settings[SETTING_FILENAME] = self.file_path if self.file_path else ''
        else:
            settings[SETTING_FILENAME] = ''

        settings[SETTING_WIN_SIZE] = self.size()
        settings[SETTING_WIN_POSE] = self.pos()
        settings[SETTING_WIN_STATE] = self.saveState()
        settings[SETTING_LINE_COLOR] = self.line_color
        settings[SETTING_FILL_COLOR] = self.fill_color
        settings[SETTING_RECENT_FILES] = self.recent_files
        settings[SETTING_ADVANCE_MODE] = not self._beginner
        if self.default_save_dir and os.path.exists(self.default_save_dir):
            settings[SETTING_SAVE_DIR] = ustr(self.default_save_dir)
        else:
            settings[SETTING_SAVE_DIR] = ''

        if self.last_open_dir and os.path.exists(self.last_open_dir):
            settings[SETTING_LAST_OPEN_DIR] = self.last_open_dir
        else:
            settings[SETTING_LAST_OPEN_DIR] = ''

        settings[SETTING_AUTO_SAVE] = self.auto_saving.isChecked()
        settings[SETTING_SINGLE_CLASS] = self.single_class_mode.isChecked()
        settings[SETTING_PAINT_LABEL] = self.display_label_option.isChecked()
        settings[SETTING_DRAW_SQUARE] = self.draw_squares_option.isChecked()
        settings[SETTING_LABEL_FILE_FORMAT] = self.label_file_format
        settings.save()

    def load_recent(self, filename):
        if self.may_continue():
            self.load_file(filename)

    def scan_all_images(self, folder_path):
        extensions = ['.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        images = []

        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relative_path = os.path.join(root, file)
                    path = ustr(os.path.abspath(relative_path))
                    images.append(path)
        natural_sort(images, key=lambda x: x.lower())
        return images

    def change_save_dir_dialog(self, _value=False):
        if self.default_save_dir is not None:
            path = ustr(self.default_save_dir)
        else:
            path = '.'

        dir_path = ustr(QFileDialog.getExistingDirectory(self,
                                                         '%s - Save annotations to the directory' % __appname__, path,
                                                         QFileDialog.ShowDirsOnly
                                                         | QFileDialog.DontResolveSymlinks))

        if dir_path is not None and len(dir_path) > 1:
            self.default_save_dir = dir_path

        self.show_bounding_box_from_annotation_file(self.file_path)

        self.statusBar().showMessage('%s . Annotation will be saved to %s' %
                                     ('Change saved folder', self.default_save_dir))
        self.statusBar().show()

    def open_annotation_dialog(self, _value=False):
        if self.file_path is None:
            self.statusBar().showMessage('Please select image first')
            self.statusBar().show()
            return

        path = os.path.dirname(ustr(self.file_path)) \
            if self.file_path else '.'
        if self.label_file_format == LabelFileFormat.PASCAL_VOC:
            filters = "Open Annotation XML file (%s)" % ' '.join(['*.xml'])
            filename = ustr(QFileDialog.getOpenFileName(self, '%s - Choose a xml file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
            self.load_pascal_xml_by_filename(filename)

        elif self.label_file_format == LabelFileFormat.CREATE_ML:

            filters = "Open Annotation JSON file (%s)" % ' '.join(['*.json'])
            filename = ustr(QFileDialog.getOpenFileName(self, '%s - Choose a json file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]

            self.load_create_ml_json_by_filename(filename, self.file_path)

    def open_dir_dialog(self, _value=False, dir_path=None, silent=False):
        if not self.may_continue():
            return

        default_open_dir_path = dir_path if dir_path else '.'
        if self.last_open_dir and os.path.exists(self.last_open_dir):
            default_open_dir_path = self.last_open_dir
        else:
            default_open_dir_path = os.path.dirname(self.file_path) if self.file_path else '.'
        if silent != True:
            target_dir_path = ustr(QFileDialog.getExistingDirectory(self,
                                                                    '%s - Open Directory' % __appname__,
                                                                    default_open_dir_path,
                                                                    QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks))
        else:
            target_dir_path = ustr(default_open_dir_path)
        self.last_open_dir = target_dir_path
        self.import_dir_images(target_dir_path)
        self.default_save_dir = target_dir_path
        if self.file_path:
            self.show_bounding_box_from_annotation_file(file_path=self.file_path)

    def import_dir_images(self, dir_path):
        if not self.may_continue() or not dir_path:
            return

        self.last_open_dir = dir_path
        self.dir_name = dir_path
        self.file_path = None
        self.file_list_widget.clear()
        self.m_img_list = self.scan_all_images(dir_path)
        self.img_count = len(self.m_img_list)
        self.open_next_image()
        for imgPath in self.m_img_list:
            item = QListWidgetItem(imgPath)
            self.file_list_widget.addItem(item)

    def verify_image(self, _value=False):
        # Proceeding next image without dialog if having any label
        if self.file_path is not None:
            try:
                self.label_file.toggle_verify()
            except AttributeError:
                # If the labelling file does not exist yet, create if and
                # re-save it with the verified attribute.
                self.save_file()
                if self.label_file is not None:
                    self.label_file.toggle_verify()
                else:
                    return

            self.canvas.verified = self.label_file.verified
            self.paint_canvas()
            self.save_file()

    def open_prev_image(self, _value=False):
        # Proceeding prev image without dialog if having any label
        if self.auto_saving.isChecked():
            if self.default_save_dir is not None:
                if self.dirty is True:
                    self.save_file()
            else:
                self.change_save_dir_dialog()
                return

        if not self.may_continue():
            return

        if self.img_count <= 0:
            return

        if self.file_path is None:
            return

        if self.cur_img_idx - 1 >= 0:
            self.cur_img_idx -= 1
            filename = self.m_img_list[self.cur_img_idx]
            if filename:
                self.load_file(filename)

    def open_next_image(self, _value=False):
        # Proceeding next image without dialog if having any label
        if self.auto_saving.isChecked():
            if self.default_save_dir is not None:
                if self.dirty is True:
                    self.save_file()
            else:
                self.change_save_dir_dialog()
                return

        if not self.may_continue():
            return

        if self.img_count <= 0:
            return

        if not self.m_img_list:
            return

        filename = None
        if self.file_path is None:
            filename = self.m_img_list[0]
            self.cur_img_idx = 0
        else:
            if self.cur_img_idx + 1 < self.img_count:
                self.cur_img_idx += 1
                filename = self.m_img_list[self.cur_img_idx]

        if filename:
            self.load_file(filename)

    def open_file(self, _value=False):
        if not self.may_continue():
            return
        path = os.path.dirname(ustr(self.file_path)) if self.file_path else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        filters = "Image & Label files (%s)" % ' '.join(formats + ['*%s' % LabelFile.suffix])
        filename, _ = QFileDialog.getOpenFileName(self, '%s - Choose Image or Label file' % __appname__, path, filters)
        if filename:
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            self.cur_img_idx = 0
            self.img_count = 1
            self.load_file(filename)

    def save_file(self, _value=False):
        if self.default_save_dir is not None and len(ustr(self.default_save_dir)):
            if self.file_path:
                image_file_name = os.path.basename(self.file_path)
                saved_file_name = os.path.splitext(image_file_name)[0]
                saved_path = os.path.join(ustr(self.default_save_dir), saved_file_name)
                self._save_file(saved_path)
        else:
            image_file_dir = os.path.dirname(self.file_path)
            image_file_name = os.path.basename(self.file_path)
            saved_file_name = os.path.splitext(image_file_name)[0]
            saved_path = os.path.join(image_file_dir, saved_file_name)
            self._save_file(saved_path if self.label_file
                            else self.save_file_dialog(remove_ext=False))

    def save_file_as(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._save_file(self.save_file_dialog())

    def save_file_dialog(self, remove_ext=True):
        caption = '%s - Choose File' % __appname__
        filters = 'File (*%s)' % LabelFile.suffix
        open_dialog_path = self.current_path()
        dlg = QFileDialog(self, caption, open_dialog_path, filters)
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        filename_without_extension = os.path.splitext(self.file_path)[0]
        dlg.selectFile(filename_without_extension)
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            full_file_path = ustr(dlg.selectedFiles()[0])
            if remove_ext:
                return os.path.splitext(full_file_path)[0]  # Return file path without the extension.
            else:
                return full_file_path
        return ''

    def _save_file(self, annotation_file_path):
        if annotation_file_path and self.save_labels(annotation_file_path):
            self.set_clean()
            self.statusBar().showMessage('Saved to  %s' % annotation_file_path)
            self.statusBar().show()

    def close_file(self, _value=False):
        if not self.may_continue():
            return
        self.reset_state()
        self.set_clean()
        self.toggle_actions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def delete_image(self):
        delete_path = self.file_path
        if delete_path is not None:
            idx = self.cur_img_idx
            if os.path.exists(delete_path):
                os.remove(delete_path)
            self.import_dir_images(self.last_open_dir)
            if self.img_count > 0:
                self.cur_img_idx = min(idx, self.img_count - 1)
                filename = self.m_img_list[self.cur_img_idx]
                self.load_file(filename)
            else:
                self.close_file()

    def reset_all(self):
        self.settings.reset()
        self.close()
        process = QProcess()
        process.startDetached(os.path.abspath(__file__))

    def may_continue(self):
        if not self.dirty:
            return True
        else:
            discard_changes = self.discard_changes_dialog()
            if discard_changes == QMessageBox.No:
                return True
            elif discard_changes == QMessageBox.Yes:
                self.save_file()
                return True
            else:
                return False

    def discard_changes_dialog(self):
        yes, no, cancel = QMessageBox.Yes, QMessageBox.No, QMessageBox.Cancel
        msg = u'You have unsaved changes, would you like to save them and proceed?\nClick "No" to undo all changes.'
        return QMessageBox.warning(self, u'Attention', msg, yes | no | cancel)

    def error_message(self, title, message):
        return QMessageBox.critical(self, title,
                                    '<p><b>%s</b></p>%s' % (title, message))

    def current_path(self):
        return os.path.dirname(self.file_path) if self.file_path else '.'

    def choose_color1(self):
        color = self.color_dialog.getColor(self.line_color, u'Choose line color',
                                           default=DEFAULT_LINE_COLOR)
        if color:
            self.line_color = color
            Shape.line_color = color
            self.canvas.set_drawing_color(color)
            self.canvas.update()
            self.set_dirty()

    def delete_selected_shape(self):
        # 检查是否处于全选模式
        if self.all_selected_mode and hasattr(self, 'canvas') and self.canvas and self.canvas.shapes:
            # 全选模式：删除所有视觉上标记为选中的形状
            shapes_to_delete = [shape for shape in self.canvas.shapes if shape.selected]
            if shapes_to_delete:
                # 显示确认对话框，默认按钮设为Yes
                reply = QMessageBox.question(
                    self, 
                    "确认删除", 
                    f"确定要删除所有 {len(shapes_to_delete)} 个检测框吗？", 
                    QMessageBox.Yes | QMessageBox.No, 
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    # 批量删除
                    deleted_count = 0
                    for shape in shapes_to_delete[:]:  # 创建副本以避免迭代过程中修改列表
                        try:
                            # 检查形状是否在shapes_to_items字典中
                            if shape in self.shapes_to_items:
                                self.remove_label(shape)
                                deleted_count += 1
                            # 从canvas的shapes列表中移除形状
                            if shape in self.canvas.shapes:
                                self.canvas.shapes.remove(shape)
                        except Exception as e:
                            print(f"Error deleting shape: {e}")
                    
                    # 重置选中状态
                    self.all_selected_mode = False
                    self.canvas.selected_shape = None
                    self.canvas.update()
                    self.set_dirty()
                    
                    QMessageBox.information(self, "删除完成", f"已删除 {deleted_count} 个检测框")
            return
        
        # 正常模式：删除单个选中的形状
        shape = self.canvas.delete_selected()
        if shape:
            self.remove_label(shape)
        self.set_dirty()
        # 如果有任何删除操作，重置全选模式
        self.all_selected_mode = False
        
        if self.no_shapes():
            for action in self.actions.onShapesPresent:
                action.setEnabled(False)

    def choose_shape_line_color(self):
        color = self.color_dialog.getColor(self.line_color, u'Choose Line Color',
                                           default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selected_shape.line_color = color
            self.canvas.update()
            self.set_dirty()

    def choose_shape_fill_color(self):
        color = self.color_dialog.getColor(self.fill_color, u'Choose Fill Color',
                                           default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selected_shape.fill_color = color
            self.canvas.update()
            self.set_dirty()

    def copy_shape(self):
        if self.canvas.selected_shape is None:
            # True if one accidentally touches the left mouse button before releasing
            return
        self.canvas.end_move(copy=True)
        self.add_label(self.canvas.selected_shape)
        self.set_dirty()

    def move_shape(self):
        self.canvas.end_move(copy=False)
        self.set_dirty()

    def load_predefined_classes(self, predef_classes_file):
        if predef_classes_file and os.path.exists(predef_classes_file):
            with codecs.open(predef_classes_file, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    if self.label_hist is None:
                        self.label_hist = [line]
                    else:
                        self.label_hist.append(line)

    def load_pascal_xml_by_filename(self, xml_path):
        if self.file_path is None:
            return
        if os.path.isfile(xml_path) is False:
            return

        self.set_format(FORMAT_PASCALVOC)

        t_voc_parse_reader = PascalVocReader(xml_path)
        shapes = t_voc_parse_reader.get_shapes()
        self.load_labels(shapes)
        self.canvas.verified = t_voc_parse_reader.verified

    def load_yolo_txt_by_filename(self, txt_path):
        if self.file_path is None:
            return
        if os.path.isfile(txt_path) is False:
            return

        self.set_format(FORMAT_YOLO)
        t_yolo_parse_reader = YoloReader(txt_path, self.image)
        shapes = t_yolo_parse_reader.get_shapes()
        print(shapes)
        self.load_labels(shapes)
        self.canvas.verified = t_yolo_parse_reader.verified

    def load_create_ml_json_by_filename(self, json_path, file_path):
        if self.file_path is None:
            return
        if os.path.isfile(json_path) is False:
            return

        self.set_format(FORMAT_CREATEML)

        create_ml_parse_reader = CreateMLReader(json_path, file_path)
        shapes = create_ml_parse_reader.get_shapes()
        self.load_labels(shapes)
        self.canvas.verified = create_ml_parse_reader.verified

    def copy_previous_bounding_boxes(self):
        current_index = self.m_img_list.index(self.file_path)
        if current_index - 1 >= 0:
            prev_file_path = self.m_img_list[current_index - 1]
            self.show_bounding_box_from_annotation_file(prev_file_path)
            self.save_file()

    def toggle_paint_labels_option(self):
        for shape in self.canvas.shapes:
            shape.paint_label = self.display_label_option.isChecked()

    def toggle_draw_square(self):
        self.canvas.set_drawing_shape_to_square(self.draw_squares_option.isChecked())

    def copy_bbox_to_other_images(self):
        """复制当前选中的检测框到其他图像"""
        if not self.canvas.selected_shape:
            QMessageBox.warning(self, "警告", "请先选择一个检测框")
            return
            
        if not self.dir_name:
            QMessageBox.warning(self, "警告", "请先打开一个图像目录")
            return
            
        # 获取要复制的检测框
        source_shape = self.canvas.selected_shape
        source_label = source_shape.label
        
        # 获取要复制到的图像数量
        try:
            copy_count = int(self.copy_count_edit.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的图像数量")
            return
            
        # 获取当前图像路径
        current_image_path = self.file_path
        if not current_image_path:
            QMessageBox.warning(self, "警告", "当前没有打开的图像")
            return
            
        # 获取目录中的所有图像文件
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
        image_files = []
        for file in os.listdir(self.dir_name):
            if any(file.lower().endswith(ext) for ext in image_extensions):
                image_files.append(os.path.join(self.dir_name, file))
        
        # 排除当前图像
        image_files = [f for f in image_files if f != current_image_path]
        
        if len(image_files) < copy_count:
            QMessageBox.warning(self, "警告", f"目录中只有{len(image_files)}张图像，少于指定的{copy_count}张")
            return
            
        # 随机选择要复制到的图像
        import random
        selected_images = random.sample(image_files, copy_count)
        
        # 获取源检测框的坐标
        source_points = [(p.x(), p.y()) for p in source_shape.points]
        source_bbox = self._get_bbox_from_points(source_points)
        
        # 读取源图像并提取检测框内容
        source_img = cv2.imread(current_image_path)
        if source_img is None:
            QMessageBox.warning(self, "错误", "无法读取源图像")
            return
            
        # 提取检测框内的图像内容
        x1, y1, x2, y2 = source_bbox
        source_roi = source_img[y1:y2, x1:x2]
        
        success_count = 0
        
        for target_image_path in selected_images:
            # 随机选择旋转角度：0, 90, 180, 270度
            rotation_angle = random.choice([0, 90, 180, 270])
            rotated_roi = self._rotate_roi(source_roi, rotation_angle)
            
            try:
                # 读取目标图像
                target_img = cv2.imread(target_image_path)
                if target_img is None:
                    continue
                    
                # 获取目标图像的标签文件路径
                target_label_path = self._get_label_path(target_image_path)
                
                # 读取现有的标签
                existing_shapes = []
                if os.path.exists(target_label_path):
                    existing_shapes = self._load_existing_labels(target_label_path, target_img.shape)
                
                # 寻找合适的位置放置检测框（避免重叠）
                new_bbox = self._find_non_overlapping_position(
                    target_img, rotated_roi, existing_shapes, source_bbox
                )
                
                if new_bbox:
                    # 将检测框内容粘贴到目标图像
                    x1, y1, x2, y2 = new_bbox
                    target_img[y1:y2, x1:x2] = rotated_roi
                    
                    # 保存修改后的图像
                    cv2.imwrite(target_image_path, target_img)
                    
                    # 添加新的标签
                    new_shape = Shape(label=source_label)
                    
                    # 根据旋转角度调整检测框坐标
                    if rotation_angle == 0:
                        # 0度：正常坐标
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[2], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[2], new_bbox[3]))
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[3]))
                    elif rotation_angle == 90:
                        # 90度顺时针：宽高互换
                        width = new_bbox[2] - new_bbox[0]
                        height = new_bbox[3] - new_bbox[1]
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[0] + height, new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[0] + height, new_bbox[1] + width))
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1] + width))
                    elif rotation_angle == 180:
                        # 180度：坐标不变
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[2], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[2], new_bbox[3]))
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[3]))
                    elif rotation_angle == 270:
                        # 270度逆时针：宽高互换
                        width = new_bbox[2] - new_bbox[0]
                        height = new_bbox[3] - new_bbox[1]
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[0] + height, new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[0] + height, new_bbox[1] + width))
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1] + width))
                    
                    new_shape.close()
                    
                    # 保存标签文件
                    self._save_label_file(target_label_path, existing_shapes + [new_shape])
                    
                    success_count += 1
                    
            except Exception as e:
                print(f"处理图像 {target_image_path} 时出错: {str(e)}")
                continue
        
        QMessageBox.information(self, "完成", f"成功复制检测框到 {success_count} 张图像")
        
    def _get_bbox_from_points(self, points):
        """从点坐标计算边界框"""
        if len(points) < 4:
            return None
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]
        return (int(min(x_coords)), int(min(y_coords)), 
                int(max(x_coords)), int(max(y_coords)))
    
    def _get_label_path(self, image_path):
        """根据图像路径获取对应的标签文件路径"""
        if self.label_file_format == LabelFileFormat.PASCAL_VOC:
            return os.path.splitext(image_path)[0] + '.xml'
        elif self.label_file_format == LabelFileFormat.YOLO:
            return os.path.splitext(image_path)[0] + '.txt'
        elif self.label_file_format == LabelFileFormat.CREATE_ML:
            return os.path.splitext(image_path)[0] + '.json'
        else:
            return os.path.splitext(image_path)[0] + '.xml'
    
    def _get_image_path_from_label(self, label_path):
        """根据标签文件路径获取对应的图像文件路径"""
        base_path = os.path.splitext(label_path)[0]
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
        
        for ext in image_extensions:
            image_path = base_path + ext
            if os.path.exists(image_path):
                return image_path
        
        # 如果找不到对应的图像文件，返回None
        return None
    
    def _load_existing_labels(self, label_path, image_shape):
        """加载现有的标签文件"""
        try:
            if self.label_file_format == LabelFileFormat.PASCAL_VOC:
                reader = PascalVocReader(label_path)
                raw_shapes = reader.get_shapes()
                
                # Pascal VOC格式也返回tuple，需要转换为Shape对象
                from libs.shape import Shape
                from PyQt5.QtCore import QPointF
                
                shapes = []
                for raw_shape in raw_shapes:
                    if len(raw_shape) >= 2:
                        label, points = raw_shape[0], raw_shape[1]
                        shape = Shape(label=label)
                        for point in points:
                            shape.add_point(QPointF(point[0], point[1]))
                        shape.close()
                        shapes.append(shape)
                
                return shapes
            elif self.label_file_format == LabelFileFormat.YOLO:
                # 为YOLO格式创建临时的QImage对象以获取图像尺寸
                from PyQt5.QtGui import QImage
                from libs.shape import Shape
                from PyQt5.QtCore import QPointF
                
                # 从image_shape创建QImage对象 (height, width, channels)
                if len(image_shape) >= 2:
                    height, width = image_shape[0], image_shape[1]
                    channels = image_shape[2] if len(image_shape) > 2 else 3
                    # 创建临时QImage对象
                    temp_image = QImage(width, height, QImage.Format_RGB888)
                    reader = YoloReader(label_path, temp_image)
                    raw_shapes = reader.get_shapes()
                    
                    # 将tuple格式转换为Shape对象
                    shapes = []
                    for raw_shape in raw_shapes:
                        if len(raw_shape) >= 2:
                            label, points = raw_shape[0], raw_shape[1]
                            shape = Shape(label=label)
                            for point in points:
                                shape.add_point(QPointF(point[0], point[1]))
                            shape.close()
                            shapes.append(shape)
                    
                    return shapes
                else:
                    return []
            elif self.label_file_format == LabelFileFormat.CREATE_ML:
                # CreateML格式需要图像路径
                image_path = self._get_image_path_from_label(label_path)
                if image_path:
                    reader = CreateMLReader(label_path, image_path)
                    raw_shapes = reader.get_shapes()
                    
                    # CreateML格式也可能返回tuple，需要转换为Shape对象
                    from libs.shape import Shape
                    from PyQt5.QtCore import QPointF
                    
                    shapes = []
                    for raw_shape in raw_shapes:
                        if len(raw_shape) >= 2:
                            label, points = raw_shape[0], raw_shape[1]
                            shape = Shape(label=label)
                            for point in points:
                                shape.add_point(QPointF(point[0], point[1]))
                            shape.close()
                            shapes.append(shape)
                    
                    return shapes
                else:
                    return []
        except Exception as e:
            print(f"加载标签文件时出错: {str(e)}")
            return []
    
    def _save_label_file(self, label_path, shapes):
        """保存标签文件"""
        try:
            if self.label_file_format == LabelFileFormat.PASCAL_VOC:
                # 创建Pascal VOC格式的标签文件
                from libs.pascal_voc_io import PascalVocWriter
                # 获取图像尺寸，这里需要从目标图像获取
                target_img_path = self._get_image_path_from_label(label_path)
                target_img = cv2.imread(target_img_path) if target_img_path else None
                if target_img is not None:
                    img_height, img_width, img_channels = target_img.shape
                    writer = PascalVocWriter(os.path.dirname(label_path), 
                                           os.path.basename(label_path), 
                                           (img_width, img_height, img_channels))
                    for shape in shapes:
                        points = [(p.x(), p.y()) for p in shape.points]
                        if len(points) >= 4:
                            writer.addBndBox(points[0][0], points[0][1], 
                                           points[2][0], points[2][1], 
                                           shape.label, shape.difficult)
                    writer.save(label_path)
            elif self.label_file_format == LabelFileFormat.YOLO:
                # 创建YOLO格式的标签文件
                target_img_path = self._get_image_path_from_label(label_path)
                target_img = cv2.imread(target_img_path) if target_img_path else None
                if target_img is not None:
                    img_height, img_width = target_img.shape[:2]
                    # 使用 'w' 模式是正确的，因为我们要保存完整的shapes列表
                    # 这里shapes包含了所有现有的标签和新的标签
                    with open(label_path, 'w') as f:
                        for shape in shapes:
                            points = [(p.x(), p.y()) for p in shape.points]
                            if len(points) >= 4:
                                # 转换为YOLO格式 (center_x, center_y, width, height)
                                center_x = (points[0][0] + points[2][0]) / 2.0 / img_width
                                center_y = (points[0][1] + points[2][1]) / 2.0 / img_height
                                width = abs(points[2][0] - points[0][0]) / img_width
                                height = abs(points[2][1] - points[0][1]) / img_height
                                f.write(f"{self._get_class_id(shape.label)} {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}\n")
            elif self.label_file_format == LabelFileFormat.CREATE_ML:
                # 创建CreateML格式的标签文件
                import json
                annotations = []
                for shape in shapes:
                    points = [(p.x(), p.y()) for p in shape.points]
                    if len(points) >= 4:
                        annotations.append({
                            "label": shape.label,
                            "coordinates": {
                                "x": (points[0][0] + points[2][0]) / 2.0,
                                "y": (points[0][1] + points[2][1]) / 2.0,
                                "width": abs(points[2][0] - points[0][0]),
                                "height": abs(points[2][1] - points[0][1])
                            }
                        })
                data = {"annotations": annotations}
                with open(label_path, 'w') as f:
                    json.dump(data, f, indent=2)
        except Exception as e:
            print(f"保存标签文件时出错: {str(e)}")
    
    def _get_class_id(self, label):
        """获取类别ID，用于YOLO格式"""
        if hasattr(self, 'label_hist') and label in self.label_hist:
            return self.label_hist.index(label)
        return 0
    
    def _find_non_overlapping_position(self, target_img, source_roi, existing_shapes, source_bbox):
        """寻找不重叠的位置放置新的检测框"""
        import random
        
        img_height, img_width = target_img.shape[:2]
        roi_height, roi_width = source_roi.shape[:2]
        
        # 尝试最多100次找到合适的位置
        max_attempts = 100
        
        for _ in range(max_attempts):
            # 随机选择位置
            x1 = random.randint(0, img_width - roi_width)
            y1 = random.randint(0, img_height - roi_height)
            x2 = x1 + roi_width
            y2 = y1 + roi_height
            
            # 检查是否与现有检测框重叠
            overlaps = False
            for shape in existing_shapes:
                shape_points = [(p.x(), p.y()) for p in shape.points]
                if len(shape_points) >= 4:
                    shape_bbox = self._get_bbox_from_points(shape_points)
                    if shape_bbox and self._check_overlap((x1, y1, x2, y2), shape_bbox):
                        overlaps = True
                        break
            
            if not overlaps:
                return (x1, y1, x2, y2)
        
        # 如果找不到合适的位置，返回None
        return None
    
    def _check_overlap(self, bbox1, bbox2):
        """检查两个边界框是否重叠"""
        if not bbox1 or not bbox2:
            return False
        
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # 计算重叠区域
        overlap_x1 = max(x1_1, x1_2)
        overlap_y1 = max(y1_1, y1_2)
        overlap_x2 = min(x2_1, x2_2)
        overlap_y2 = min(y2_1, y2_2)
        
        # 如果有重叠区域，计算重叠面积
        if overlap_x1 < overlap_x2 and overlap_y1 < overlap_y2:
            overlap_area = (overlap_x2 - overlap_x1) * (overlap_y2 - overlap_y1)
            bbox1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
            bbox2_area = (x2_2 - x1_2) * (y2_2 - y1_2)
            
            # 如果重叠面积超过任一检测框面积的20%，认为重叠
            overlap_ratio = overlap_area / min(bbox1_area, bbox2_area)
            return overlap_ratio > 0.2
        
        return False

    def copy_all_bbox_randomly(self):
        """从当前目录下所有图像中收集检测框，随机复制到其他图像"""
        if not self.dir_name:
            QMessageBox.warning(self, "警告", "请先打开一个图像目录")
            return
            
        # 获取要复制到的图像数量
        try:
            copy_count = int(self.copy_count_edit.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的图像数量")
            return
            
        # 获取目录中的所有图像文件
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
        all_image_files = []
        for file in os.listdir(self.dir_name):
            if any(file.lower().endswith(ext) for ext in image_extensions):
                all_image_files.append(os.path.join(self.dir_name, file))
        
        if len(all_image_files) < copy_count + 1:  # +1 因为需要排除源图像
            QMessageBox.warning(self, "警告", f"目录中图像数量不足")
            return
        
        # 收集当前目录下所有图像的检测框信息
        all_bbox_info = []  # 存储 (图像路径, 检测框信息, 标签)
        
        for image_path in all_image_files:
            label_path = self._get_label_path(image_path)
            if os.path.exists(label_path):
                try:
                    # 读取图像获取尺寸
                    img = cv2.imread(image_path)
                    if img is not None:
                        shapes = self._load_existing_labels(label_path, img.shape)
                        for shape in shapes:
                            shape_points = [(p.x(), p.y()) for p in shape.points]
                            bbox = self._get_bbox_from_points(shape_points)
                            if bbox:
                                all_bbox_info.append((image_path, bbox, shape.label))
                except Exception as e:
                    print(f"处理图像 {image_path} 时出错: {str(e)}")
                    continue
        
        if not all_bbox_info:
            QMessageBox.warning(self, "警告", "当前目录下没有找到任何检测框")
            return
        
        # 随机选择检测框进行复制（使用更合理的数量）
        import random
        # 计算要复制的检测框数量：取用户设置数量和检测框总数的较小值
        num_to_copy = min(copy_count, len(all_bbox_info))
        if num_to_copy == 0:
            QMessageBox.warning(self, "警告", "没有可用的检测框进行复制")
            return
            
        selected_bboxes = random.sample(all_bbox_info, num_to_copy)
        
        # 随机选择目标图像
        selected_images = random.sample(all_image_files, copy_count)
        
        # 打乱检测框顺序，确保随机分配
        random.shuffle(selected_bboxes)
        
        success_count = 0
        
        # 将检测框分散分配到不同的图像上
        for i, (source_image_path, source_bbox, source_label) in enumerate(selected_bboxes):
            try:
                # 随机选择旋转角度：0, 90, 180, 270度
                rotation_angle = random.choice([0, 90, 180, 270])
                
                # 计算目标图像索引，确保均匀分布
                target_image_index = i % copy_count
                target_image_path = selected_images[target_image_index]
                
                # 读取目标图像
                target_img = cv2.imread(target_image_path)
                if target_img is None:
                    continue
                    
                # 获取目标图像的标签文件路径
                target_label_path = self._get_label_path(target_image_path)
                
                # 读取现有的标签
                existing_shapes = []
                if os.path.exists(target_label_path):
                    existing_shapes = self._load_existing_labels(target_label_path, target_img.shape)
                
                # 读取源图像并提取检测框内容
                source_img = cv2.imread(source_image_path)
                if source_img is None:
                    continue
                
                # 提取检测框内的图像内容
                x1, y1, x2, y2 = source_bbox
                source_roi = source_img[y1:y2, x1:x2]
                
                # 应用旋转
                rotated_roi = self._rotate_roi(source_roi, rotation_angle)
                
                # 寻找合适的位置放置检测框（避免重叠）
                new_bbox = self._find_non_overlapping_position(
                    target_img, rotated_roi, existing_shapes, source_bbox
                )
                
                if new_bbox:
                    # 将检测框内容粘贴到目标图像
                    x1, y1, x2, y2 = new_bbox
                    target_img[y1:y2, x1:x2] = rotated_roi
                    
                    # 保存修改后的图像
                    cv2.imwrite(target_image_path, target_img)
                    
                    # 添加新的标签
                    new_shape = Shape(label=source_label)
                    
                    # 根据旋转角度调整检测框坐标
                    if rotation_angle == 0:
                        # 0度：正常坐标
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[2], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[2], new_bbox[3]))
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[3]))
                    elif rotation_angle == 90:
                        # 90度顺时针：宽高互换
                        width = new_bbox[2] - new_bbox[0]
                        height = new_bbox[3] - new_bbox[1]
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[0] + height, new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[0] + height, new_bbox[1] + width))
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1] + width))
                    elif rotation_angle == 180:
                        # 180度：坐标不变
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[2], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[2], new_bbox[3]))
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[3]))
                    elif rotation_angle == 270:
                        # 270度逆时针：宽高互换
                        width = new_bbox[2] - new_bbox[0]
                        height = new_bbox[3] - new_bbox[1]
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[0] + height, new_bbox[1]))
                        new_shape.add_point(QPointF(new_bbox[0] + height, new_bbox[1] + width))
                        new_shape.add_point(QPointF(new_bbox[0], new_bbox[1] + width))
                    
                    new_shape.close()
                    
                    # 保存标签文件
                    self._save_label_file(target_label_path, existing_shapes + [new_shape])
                    
                    success_count += 1
                    
            except Exception as e:
                print(f"处理图像 {target_image_path} 时出错: {str(e)}")
                continue
        
        QMessageBox.information(self, "完成", f"成功从目录中随机复制检测框到 {success_count} 张图像")

    def generate_rotation_augmentation(self):
        """生成当前图像的旋转增强版本"""
        if not self.file_path:
            QMessageBox.warning(self, "Warning", "请先加载一张图像。")
            return
        
        # 检查标签数据
        shapes = []
        
        # 标签数据存储在self.canvas.shapes中
        if self.canvas and hasattr(self.canvas, 'shapes') and self.canvas.shapes:
            shapes = self.canvas.shapes
        else:
            # 尝试从当前图像对应的标签文件中读取
            image_path = self.file_path
            if self.default_save_dir:
                basename = os.path.splitext(os.path.basename(image_path))[0]
                if self.label_file_format == LabelFileFormat.YOLO:
                    label_path = os.path.join(self.default_save_dir, basename + TXT_EXT)
                elif self.label_file_format == LabelFileFormat.PASCAL_VOC:
                    label_path = os.path.join(self.default_save_dir, basename + XML_EXT)
                elif self.label_file_format == LabelFileFormat.CREATE_ML:
                    label_path = os.path.join(self.default_save_dir, basename + JSON_EXT)
                
                if os.path.exists(label_path):
                    try:
                        # 重新加载标签文件
                        self.label_file = LabelFile(label_path)
                        shapes = self.label_file.shapes
                    except Exception as e:
                        pass
        
        if not shapes:
            QMessageBox.warning(self, "Warning", "当前图像没有标签数据。请先绘制一些边界框。")
            return
        
        try:
            aug_count = int(self.aug_count_edit.text())
            rotation_range = int(self.rotation_range_edit.text())
        except ValueError:
            QMessageBox.warning(self, "Warning", "请输入有效的增强数量和旋转角度范围。")
            return
        
        # 获取当前图像路径
        image_path = self.file_path
        
        # 读取图像
        image = cv2.imread(image_path)
        if image is None:
            QMessageBox.warning(self, "Warning", "读取图像失败。")
            return
        
        # 获取图像尺寸
        height, width = image.shape[:2]
        
        # 保存到当前图像所在的文件夹
        save_dir = os.path.dirname(image_path)
        
        success_count = 0
        
        try:
            import albumentations as A
            use_albumentations = True
        except ImportError:
            use_albumentations = False
            print("警告: 未安装albumentations库，将使用OpenCV进行旋转（精度较低）")
        
        for i in range(aug_count):
            # 随机生成旋转角度
            angle = random.uniform(-rotation_range, rotation_range)
            
            if use_albumentations:
                # 使用albumentations库进行精确的旋转和坐标变换
                transform = A.Compose([
                    A.Rotate(limit=angle, p=1.0, border_mode=cv2.BORDER_CONSTANT, value=0)
                ], bbox_params=A.BboxParams(format='pascal_voc', label_fields=['class_labels']))
                
                # 准备边界框数据
                bboxes = []
                class_labels = []
                for shape in shapes:
                    points = shape.points
                    if len(points) >= 2:
                        # 计算边界框
                        x_coords = [p.x() for p in points]
                        y_coords = [p.y() for p in points]
                        x_min, x_max = min(x_coords), max(x_coords)
                        y_min, y_max = min(y_coords), max(y_coords)
                        
                        # 转换为Pascal VOC格式 (x_min, y_min, x_max, y_max)
                        # 这是albumentations期望的格式
                        bboxes.append([x_min, y_min, x_max, y_max])
                        class_labels.append(shape.label)
                
                # 应用变换
                transformed = transform(image=image, bboxes=bboxes, class_labels=class_labels)
                rotated_image = transformed['image']
                transformed_bboxes = transformed['bboxes']
                
                # 生成增强后的文件名
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                aug_image_name = f"{base_name}_aug_{i+1:02d}.jpg"
                aug_image_path = os.path.join(save_dir, aug_image_name)
                
                # 保存增强后的图像
                cv2.imwrite(aug_image_path, rotated_image)
                
                # 处理标签坐标
                if self.label_file_format == LabelFileFormat.YOLO:
                    # YOLO格式：归一化坐标 (x_center, y_center, width, height)
                    aug_labels = []
                    for bbox, class_label in zip(transformed_bboxes, class_labels):
                        x_min, y_min, x_max, y_max = bbox
                        
                        # 转换为YOLO格式
                        x_center = (x_min + x_max) / 2
                        y_center = (y_min + y_max) / 2
                        w = x_max - x_min
                        h = y_max - y_min
                        
                        # 归一化坐标
                        x_center_norm = x_center / width
                        y_center_norm = y_center / height
                        w_norm = w / width
                        h_norm = h / height
                        
                        # 确保坐标在有效范围内
                        x_center_norm = max(0, min(1, x_center_norm))
                        y_center_norm = max(0, min(1, y_center_norm))
                        w_norm = max(0, min(1, w_norm))
                        h_norm = max(0, min(1, h_norm))
                        
                        # 获取类别索引
                        class_list = self._get_class_list()
                        if class_label in class_list:
                            class_index = class_list.index(class_label)
                        else:
                            class_index = 0
                        
                        aug_labels.append(f"{class_index} {x_center_norm:.6f} {y_center_norm:.6f} {w_norm:.6f} {h_norm:.6f}")
                    
                    # 保存增强后的标签文件
                    aug_label_name = f"{base_name}_aug_{i+1:02d}.txt"
                    aug_label_path = os.path.join(save_dir, aug_label_name)
                    with open(aug_label_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(aug_labels))
                
                elif self.label_file_format == LabelFileFormat.PASCAL_VOC:
                    # Pascal VOC格式：XML文件
                    aug_label_name = f"{base_name}_aug_{i+1:02d}.xml"
                    aug_label_path = os.path.join(save_dir, aug_label_name)
                    self._save_pascal_voc_augmented_albumentations(shapes, transformed_bboxes, aug_label_path, aug_image_path, width, height, class_labels)
            
            else:
                # 使用OpenCV进行旋转（精度较低）
                # 计算旋转矩阵
                center = (width // 2, height // 2)
                rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
                
                # 执行图像旋转
                rotated_image = cv2.warpAffine(image, rotation_matrix, (width, height))
                
                # 生成增强后的文件名
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                aug_image_name = f"{base_name}_aug_{i+1:02d}.jpg"
                aug_image_path = os.path.join(save_dir, aug_image_name)
                
                # 保存增强后的图像
                cv2.imwrite(aug_image_path, rotated_image)
                
                # 处理标签坐标（使用改进的OpenCV方法）
                if self.label_file_format == LabelFileFormat.YOLO:
                    aug_labels = []
                    for shape in shapes:
                        points = shape.points
                        if len(points) >= 2:
                            # 计算边界框
                            x_coords = [p.x() for p in points]
                            y_coords = [p.y() for p in points]
                            x_min, x_max = min(x_coords), max(x_coords)
                            y_min, y_max = min(y_coords), max(y_coords)
                            
                            # 转换为YOLO格式
                            x_center = (x_min + x_max) / 2 / width
                            y_center = (y_min + y_max) / 2 / height
                            w = (x_max - x_min) / width
                            h = (y_max - y_min) / height
                            
                            # 使用改进的旋转坐标计算
                            rotated_x_center, rotated_y_center = self._rotate_bbox_improved(
                                x_center * width, y_center * height, w * width, h * height, center, angle
                            )
                            
                            # 重新归一化
                            rotated_x_center = max(0, min(1, rotated_x_center / width))
                            rotated_y_center = max(0, min(1, rotated_y_center / height))
                            
                            # 获取类别索引
                            label = shape.label
                            class_list = self._get_class_list()
                            if label in class_list:
                                class_index = class_list.index(label)
                            else:
                                class_index = 0
                            
                            aug_labels.append(f"{class_index} {rotated_x_center:.6f} {rotated_y_center:.6f} {w:.6f} {h:.6f}")
                    
                    # 保存增强后的标签文件
                    aug_label_name = f"{base_name}_aug_{i+1:02d}.txt"
                    aug_label_path = os.path.join(save_dir, aug_label_name)
                    with open(aug_label_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(aug_labels))
                
                elif self.label_file_format == LabelFileFormat.PASCAL_VOC:
                    # Pascal VOC格式：XML文件
                    aug_label_name = f"{base_name}_aug_{i+1:02d}.xml"
                    aug_label_path = os.path.join(save_dir, aug_label_name)
                    self._save_pascal_voc_augmented(shapes, aug_label_path, aug_image_path, width, height, center, angle)
            
            success_count += 1
        
        # 显示完成消息
        result_msg = f"旋转增强完成！\n\n"
        result_msg += f"增强数量: {success_count}\n"
        result_msg += f"旋转角度范围: ±{rotation_range}°\n"
        result_msg += f"保存位置: {save_dir}"
        
        QMessageBox.information(self, "旋转增强完成", result_msg)
    
    def _rotate_point(self, x, y, center, angle):
        """旋转点坐标"""
        import math
        cx, cy = center
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        # 平移到原点
        x -= cx
        y -= cy
        
        # 旋转
        new_x = x * cos_a - y * sin_a
        new_y = x * sin_a + y * cos_a
        
        # 平移回原位置
        new_x += cx
        new_y += cy
        
        return new_x, new_y
    
    def _rotate_bbox_improved(self, x_center, y_center, width, height, center, angle):
        """改进的边界框旋转方法"""
        import math
        cx, cy = center
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        # 计算边界框的四个角点
        corners = [
            (x_center - width/2, y_center - height/2),  # 左上
            (x_center + width/2, y_center - height/2),  # 右上
            (x_center + width/2, y_center + height/2),  # 右下
            (x_center - width/2, y_center + height/2)   # 左下
        ]
        
        # 旋转所有角点
        rotated_corners = []
        for x, y in corners:
            # 平移到原点
            x -= cx
            y -= cy
            
            # 旋转
            new_x = x * cos_a - y * sin_a
            new_y = x * sin_a + y * cos_a
            
            # 平移回原位置
            new_x += cx
            new_y += cy
            
            rotated_corners.append((new_x, new_y))
        
        # 计算旋转后的边界框中心点和尺寸
        x_coords = [x for x, y in rotated_corners]
        y_coords = [y for x, y in rotated_corners]
        
        new_x_center = (min(x_coords) + max(x_coords)) / 2
        new_y_center = (min(y_coords) + max(y_coords)) / 2
        new_width = max(x_coords) - min(x_coords)
        new_height = max(y_coords) - min(y_coords)
        
        return new_x_center, new_y_center
    
    def _get_class_list(self):
        """获取类别列表"""
        if hasattr(self, 'label_hist') and self.label_hist:
            return self.label_hist
        else:
            # 如果没有预定义类别，返回默认类别
            return ['object']
    
    def _save_pascal_voc_augmented(self, shapes, label_path, image_path, width, height, center, angle):
        """保存Pascal VOC格式的增强标签"""
        try:
            from libs.pascal_voc_io import PascalVocWriter
            
            img_folder_name = os.path.basename(os.path.dirname(image_path))
            img_file_name = os.path.basename(image_path)
            image_shape = [height, width, 3]
            
            writer = PascalVocWriter(img_folder_name, img_file_name, image_shape, local_img_path=image_path)
            writer.verified = self.label_file.verified if self.label_file else False
            
            for shape in shapes:
                points = shape.points  # 使用shape.points而不是shape['points']
                label = shape.label  # 使用shape.label而不是shape['label']
                difficult = int(shape.difficult if hasattr(shape, 'difficult') else 0)
                
                # 旋转边界框坐标
                rotated_points = []
                for point in points:
                    rotated_x, rotated_y = self._rotate_point(point.x(), point.y(), center, angle)
                    rotated_points.append([rotated_x, rotated_y])
                
                # 计算旋转后的边界框
                x_coords = [p[0] for p in rotated_points]
                y_coords = [p[1] for p in rotated_points]
                x_min = max(0, min(x_coords))
                y_min = max(0, min(y_coords))
                x_max = min(width, max(x_coords))
                y_max = min(height, max(y_coords))
                
                # 确保边界框在图像范围内
                if x_max > x_min and y_max > y_min:
                    writer.add_bnd_box(x_min, y_min, x_max, y_max, label, difficult)
            
            writer.save(target_file=label_path)
            
        except Exception as e:
            print(f"保存Pascal VOC格式标签时出错: {str(e)}")
    
    def _save_pascal_voc_augmented_albumentations(self, shapes, transformed_bboxes, label_path, image_path, width, height, class_labels):
        """使用albumentations结果保存Pascal VOC格式的增强标签"""
        try:
            from libs.pascal_voc_io import PascalVocWriter
            
            img_folder_name = os.path.basename(os.path.dirname(image_path))
            img_file_name = os.path.basename(image_path)
            image_shape = [height, width, 3]
            
            writer = PascalVocWriter(img_folder_name, img_file_name, image_shape, local_img_path=image_path)
            writer.verified = self.label_file.verified if self.label_file else False
            
            for bbox, class_label in zip(transformed_bboxes, class_labels):
                x_min, y_min, x_max, y_max = bbox
                
                # 确保边界框在图像范围内
                x_min = max(0, min(width, x_min))
                y_min = max(0, min(height, y_min))
                x_max = max(0, min(width, x_max))
                y_max = max(0, min(height, y_max))
                
                # 确保边界框有效
                if x_max > x_min and y_max > y_min:
                    writer.add_bnd_box(x_min, y_min, x_max, y_max, class_label, 0)
            
            writer.save(target_file=label_path)
            
        except Exception as e:
            print(f"保存Pascal VOC格式标签时出错: {str(e)}")
    
    def copy_images_with_bbox(self):
        """自动识别整个目录下所有图像和检测框，复制指定数量的图像，随机保留指定百分比的检测框"""
        if not self.dir_name:
            QMessageBox.warning(self, "警告", "请先打开一个图像目录")
            return
        
        # 获取用户设置的参数
        try:
            copy_count = int(self.copy_count_edit_2.text())
            bbox_keep_percent = int(self.bbox_keep_edit.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的数量和百分比")
            return
        
        if copy_count < 1 or copy_count > 100:
            QMessageBox.warning(self, "警告", "复制数量必须在1-100之间")
            return
        
        if bbox_keep_percent < 1 or bbox_keep_percent > 100:
            QMessageBox.warning(self, "警告", "检测框保留百分比必须在1-100之间")
            return
        
        # 获取目录中的所有图像文件
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
        all_image_files = []
        for file in os.listdir(self.dir_name):
            if any(file.lower().endswith(ext) for ext in image_extensions):
                all_image_files.append(os.path.join(self.dir_name, file))
        
        if not all_image_files:
            QMessageBox.warning(self, "警告", "目录中没有找到图像文件")
            return
        
        # 收集所有图像的检测框信息
        all_images_with_bbox = []  # 存储 (图像路径, 检测框列表, 标签列表)
        
        for image_path in all_image_files:
            label_path = self._get_label_path(image_path)
            if os.path.exists(label_path):
                try:
                    # 读取图像获取尺寸
                    img = cv2.imread(image_path)
                    if img is not None:
                        shapes = self._load_existing_labels(label_path, img.shape)
                        if shapes:  # 只处理有检测框的图像
                            all_images_with_bbox.append((image_path, shapes, img))
                except Exception as e:
                    print(f"处理图像 {image_path} 时出错: {str(e)}")
                    continue
        
        if not all_images_with_bbox:
            QMessageBox.warning(self, "警告", "目录中没有找到包含检测框的图像")
            return
        
        # 直接使用当前目录，不创建子文件夹
        output_dir = self.dir_name
        
        success_count = 0
        
        # 为每张有检测框的图像创建指定数量的副本
        for source_image_path, source_shapes, source_img in all_images_with_bbox:
            base_name = os.path.splitext(os.path.basename(source_image_path))[0]
            
            for i in range(copy_count):
                try:
                    # 创建新的图像文件名
                    new_image_name = f"{base_name}_aug_{i+1:03d}.jpg"
                    new_image_path = os.path.join(output_dir, new_image_name)
                    
                    # 复制图像
                    new_img = source_img.copy()
                    
                    # 计算要保留的检测框数量（向上取整）
                    total_bboxes = len(source_shapes)
                    keep_count = max(1, int((total_bboxes * bbox_keep_percent + 99) / 100))  # 向上取整
                    
                    # 随机选择要保留的检测框
                    import random
                    selected_shapes = random.sample(source_shapes, min(keep_count, total_bboxes))
                    
                    # 创建新的标签文件
                    new_label_path = self._get_label_path(new_image_path)
                    
                    # 保存新图像
                    cv2.imwrite(new_image_path, new_img)
                    
                    # 保存新的标签文件
                    self._save_label_file(new_label_path, selected_shapes)
                    
                    success_count += 1
                    
                except Exception as e:
                    print(f"创建图像副本 {new_image_name} 时出错: {str(e)}")
                    continue
        
        QMessageBox.information(self, "完成", f"成功创建 {success_count} 张增强图像到 {output_dir} 目录")
    
    def unify_bbox_sizes(self):
        """统一调整目录下所有标签的宽高为设定的值，保持检测框中心点不变"""
        if not self.dir_name:
            QMessageBox.warning(self, "警告", "请先打开一个图像目录")
            return
        
        # 获取用户设置的宽高值
        try:
            target_width = int(self.block_width_edit.text())
            target_height = int(self.block_height_edit.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的宽高值")
            return
        
        if target_width < 10 or target_width > 1000 or target_height < 10 or target_height > 1000:
            QMessageBox.warning(self, "警告", "宽高值必须在10-1000之间")
            return
        
        # 直接执行，不显示确认弹窗
        
        # 获取目录中的所有图像文件
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
        all_image_files = []
        for file in os.listdir(self.dir_name):
            if any(file.lower().endswith(ext) for ext in image_extensions):
                all_image_files.append(os.path.join(self.dir_name, file))
        
        if not all_image_files:
            QMessageBox.warning(self, "警告", "目录中没有找到图像文件")
            return
        
        # 统计需要处理的标签文件
        processed_count = 0
        modified_count = 0
        
        for image_path in all_image_files:
            label_path = self._get_label_path(image_path)
            if os.path.exists(label_path):
                try:
                    # 读取图像获取尺寸
                    img = cv2.imread(image_path)
                    if img is not None:
                        shapes = self._load_existing_labels(label_path, img.shape)
                        if shapes:
                            processed_count += 1
                            
                            # 修改每个检测框的尺寸
                            modified_shapes = []
                            for shape in shapes:
                                # 计算当前检测框的中心点
                                shape_points = [(p.x(), p.y()) for p in shape.points]
                                if len(shape_points) >= 4:
                                    current_bbox = self._get_bbox_from_points(shape_points)
                                    if current_bbox:
                                        x1, y1, x2, y2 = current_bbox
                                        center_x = (x1 + x2) / 2
                                        center_y = (y1 + y2) / 2
                                        
                                        # 计算新的边界框，保持中心点不变
                                        new_x1 = int(center_x - target_width / 2)
                                        new_y1 = int(center_y - target_height / 2)
                                        new_x2 = int(center_x + target_width / 2)
                                        new_y2 = int(center_y + target_height / 2)
                                        
                                        # 确保边界框在图像范围内
                                        img_height, img_width = img.shape[:2]
                                        new_x1 = max(0, min(img_width - target_width, new_x1))
                                        new_y1 = max(0, min(img_height - target_height, new_y1))
                                        new_x2 = new_x1 + target_width
                                        new_y2 = new_y1 + target_height
                                        
                                        # 创建新的Shape对象
                                        new_shape = Shape(label=shape.label)
                                        new_shape.add_point(QPointF(new_x1, new_y1))
                                        new_shape.add_point(QPointF(new_x2, new_y1))
                                        new_shape.add_point(QPointF(new_x2, new_y2))
                                        new_shape.add_point(QPointF(new_x1, new_y2))
                                        new_shape.close()
                                        
                                        modified_shapes.append(new_shape)
                                    else:
                                        # 如果无法获取边界框，保持原样
                                        modified_shapes.append(shape)
                                else:
                                    # 如果点数不足，保持原样
                                    modified_shapes.append(shape)
                            
                            # 保存修改后的标签文件
                            if modified_shapes:
                                self._save_label_file(label_path, modified_shapes)
                                modified_count += 1
                                
                except Exception as e:
                    print(f"处理标签文件 {label_path} 时出错: {str(e)}")
                    continue
        
        if processed_count == 0:
            QMessageBox.information(self, "完成", "目录中没有找到需要处理的标签文件")
        else:
            QMessageBox.information(self, "完成", f"成功处理 {processed_count} 个标签文件，修改了 {modified_count} 个文件")
    
    def toggle_group_box(self, group_box, checked):
        """切换GroupBox的折叠/展开状态"""
        if checked:
            # 展开
            group_box.setMaximumHeight(16777215)  # 设置一个很大的值来取消高度限制
        else:
            # 折叠
            group_box.setMaximumHeight(30)

    def _rotate_roi(self, roi, angle):
        """旋转ROI图像，角度为0, 90, 180, 270度"""
        if angle == 0:
            return roi
        elif angle == 90:
            return cv2.rotate(roi, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(roi, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(roi, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            return roi

    def _rotate_bbox_coordinates(self, bbox, roi_width, roi_height, angle):
        """根据旋转角度计算检测框的新坐标"""
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        
        if angle == 0:
            return bbox
        elif angle == 90:
            # 90度顺时针旋转：宽高互换，坐标重新计算
            new_width = height
            new_height = width
            new_x1 = x1
            new_y1 = y1
            new_x2 = x1 + new_width
            new_y2 = y1 + new_height
            return (new_x1, new_y1, new_x2, new_y2)
        elif angle == 180:
            # 180度旋转：坐标不变，但需要调整位置
            return bbox
        elif angle == 270:
            # 270度逆时针旋转：宽高互换，坐标重新计算
            new_width = height
            new_height = width
            new_x1 = x1
            new_y1 = y1
            new_x2 = x1 + new_width
            new_y2 = y1 + new_height
            return (new_x1, new_y1, new_x2, new_y2)
        else:
            return bbox


    def add_fixed_size_block(self):
        """启用固定大小区块创建模式"""
        self.canvas.set_drawing_mode('fixed')
        self.canvas.set_editing(False)  # 进入绘制模式
        self.statusBar().showMessage("请点击画布创建固定大小区块（默认35x35）")
    
    def add_freehand_block(self):
        """启用不规则选区创建模式"""
        self.canvas.set_drawing_mode('freehand')
        self.canvas.set_editing(False)  # 进入绘制模式
        self.statusBar().showMessage("请在画布上点击多个点创建不规则选区，最后一个点靠近起点时自动闭合")
    
    def cut_selected_bbox(self):
        """切割当前选择的检测框为设定的小尺寸"""
        if not self.canvas.selected_shape:
            QMessageBox.warning(self, "警告", "请先选择一个检测框")
            return
        
        # 使用固定的切割尺寸35×35
        cut_width = 35
        cut_height = 35
        
        # 获取当前选择的检测框信息
        shape_points = [(p.x(), p.y()) for p in self.canvas.selected_shape.points]
        if len(shape_points) < 4:
            QMessageBox.warning(self, "警告", "检测框格式不正确")
            return
        
        # 计算不规则图形的最小外接矩形
        min_x = min(p[0] for p in shape_points)
        max_x = max(p[0] for p in shape_points)
        min_y = min(p[1] for p in shape_points)
        max_y = max(p[1] for p in shape_points)
        
        current_width = max_x - min_x
        current_height = max_y - min_y
        
        # 检查切割尺寸是否合理
        if cut_width > current_width or cut_height > current_height:
            QMessageBox.warning(self, "警告", f"切割尺寸不能大于原检测框尺寸\n原尺寸: {current_width}x{current_height}\n切割尺寸: {cut_width}x{cut_height}")
            return
        
        # 计算可以切割的数量（向下取整）
        max_cuts_x = current_width // cut_width
        max_cuts_y = current_height // cut_height
        total_cuts = max_cuts_x * max_cuts_y
        
        if total_cuts == 0:
            QMessageBox.warning(self, "警告", "检测框太小，无法切割")
            return
        
        # 计算剩余空间和间隙大小
        remaining_width = current_width - max_cuts_x * cut_width
        remaining_height = current_height - max_cuts_y * cut_height
        
        # 计算间隙大小（间隙数量比切割块多1）
        gap_x = remaining_width // (max_cuts_x + 1) if max_cuts_x > 0 else 0
        gap_y = remaining_height // (max_cuts_y + 1) if max_cuts_y > 0 else 0
        
        # 显示确认弹窗
        reply = QMessageBox.question(
            self, 
            "确认切割", 
            f"确定要将检测框切割成 {cut_width}x{cut_height} 的小块吗？\n\n"
            f"可以切割 {max_cuts_x}x{max_cuts_y} = {total_cuts} 个小块\n"
            f"水平间隙: {gap_x}px, 垂直间隙: {gap_y}px\n"
            f"原检测框将被删除，替换为切割后的小块", 
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 执行切割操作
        self._perform_bbox_cutting(
            min_x, min_y, max_x, max_y, 
            cut_width, cut_height, 
            max_cuts_x, max_cuts_y,
            gap_x, gap_y
        )

    def select_all_shapes(self):
        """全选并删除所有检测框"""
        # 确保canvas存在且有形状
        if not hasattr(self, 'canvas') or not self.canvas or not self.canvas.shapes:
            return
            
        try:
            total_shapes = len(self.canvas.shapes)
            
            # 显示确认删除对话框，默认按钮设置为Yes（删除）
            reply = QMessageBox.question(
                self, 
                "确认删除", 
                f"确定要删除所有 {total_shapes} 个检测框吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes  # 默认按钮设为Yes
            )
            
            if reply == QMessageBox.Yes:
                # 清空所有形状
                self.canvas.shapes = []
                self.label_list.clear()
                
                # 更新shapes_to_items映射
                self.shapes_to_items = {}
                self.items_to_shapes = {}
                
                # 更新画布显示
                self.canvas.update()
                self.canvas.repaint()
                self.set_dirty()
                
                # 显示删除完成提示
                QMessageBox.information(self, "删除完成", f"已成功删除所有 {total_shapes} 个检测框")
        except Exception as e:
            print(f"Error selecting and deleting all shapes: {e}")
    
    def _perform_bbox_cutting(self, min_x, min_y, max_x, max_y, 
                            cut_width, cut_height, 
                            max_cuts_x, max_cuts_y,
                            gap_x, gap_y):
        """执行行错位分割操作，只实现行的错位排列，确保区块之间有间隙"""
        # 保存原始形状的标签和复制原始形状
        original_shape = self.canvas.selected_shape
        original_label = original_shape.label if original_shape else ""
        
        # 复制原始形状用于后续重叠度计算
        import copy
        original_shape_copy = copy.deepcopy(original_shape)
        
        # 删除原始检测框
        self.canvas.delete_selected()
        
        # 创建新的小检测框
        new_shapes = []
        
        # 导入Shape类
        from libs.shape import Shape
        
        # 使用固定的间隙大小，而不是自适应
        # 确保区块之间有间隙，但在选区内没有重叠
        actual_gap_x = max(gap_x, 2)  # 至少2像素的间隙
        actual_gap_y = max(gap_y, 2)
        
        # 设置行偏移比例（可以根据需要调整）
        row_offset_ratio = 0.5  # 奇数行向右偏移区块宽度的50%
        
        # 计算实际的网格布局参数
        # 计算网格的起始位置（考虑间隙）
        grid_start_x = min_x + actual_gap_x
        grid_start_y = min_y + actual_gap_y
        
        # 计算网格的实际步长（包含间隙）
        grid_step_x = cut_width + actual_gap_x
        grid_step_y = cut_height + actual_gap_y
        
        # 计算网格的实际大小（确保不超出最大边界）
        # 考虑行错位布局可能需要的额外空间
        available_width = max_x - grid_start_x
        available_height = max_y - grid_start_y
        
        # 计算网格的实际列数和行数
        actual_cols = int(available_width / grid_step_x) + 1
        actual_rows = int(available_height / grid_step_y) + 1
        
        # 遍历网格布局，创建行错位的无重叠区块
        for row in range(actual_rows):
            # 计算行偏移（奇数行向右偏移）
            row_offset = cut_width * row_offset_ratio if row % 2 == 1 else 0
            
            for col in range(actual_cols):
                # 计算当前区块的坐标（考虑行偏移）
                x1 = grid_start_x + col * grid_step_x + row_offset
                y1 = grid_start_y + row * grid_step_y
                x2 = x1 + cut_width
                y2 = y1 + cut_height
                
                # 确保区块不超出最大边界
                if x2 > max_x or y2 > max_y:
                    continue
                
                # 计算这个区块与原始选区的重叠度
                overlap_ratio = self._calculate_overlap_ratio(
                    x1, y1, x2, y2, original_shape_copy)
                
                # 使用45%/55%的重叠度阈值规则明确处理边界
                # 1. 重叠超过45%的区块保留
                # 2. 重叠低于45%的区块不保留
                # 3. 重叠在45%-55%之间的区块也不保留
                # 这样可以在边界形成清晰的切割效果
                if overlap_ratio >= 0.45:  # 只保留重叠度>=45%的区块
                    # 创建新形状
                    new_shape = Shape()
                    new_shape.add_point(QPointF(x1, y1))
                    new_shape.add_point(QPointF(x2, y1))
                    new_shape.add_point(QPointF(x2, y2))
                    new_shape.add_point(QPointF(x1, y2))
                    new_shape.close()
                    new_shape.label = original_label
                    
                    # 添加到新形状列表
                    new_shapes.append(new_shape)
        
        # 关键修复：确保新创建的形状被正确添加到画布
        if new_shapes:  # 只有当有新形状创建时才执行添加操作
            for shape in new_shapes:
                self.canvas.shapes.append(shape)
                self.add_label(shape)
            
            # 立即更新画布显示
            self.canvas.repaint()
            self.set_dirty()
            
            # 显示切割完成的提示信息
            QMessageBox.information(self, "切割完成", f"已将检测框切割为 {len(new_shapes)} 个小检测框")
    
    def _calculate_overlap_ratio(self, x1, y1, x2, y2, original_shape, sample_step=5):
        """计算矩形块与原始形状的重叠像素比例"""
        overlap_pixels = 0
        total_pixels = 0
        
        # 使用适当的采样步长进行计算
        for px in range(int(x1), int(x2), sample_step):
            for py in range(int(y1), int(y2), sample_step):
                total_pixels += 1
                # 检查点是否在原始选区的边界上或内部
                if original_shape.contains_point(QPointF(px, py)):
                    overlap_pixels += 1
        
        # 返回重叠比例
        return overlap_pixels / total_pixels if total_pixels > 0 else 0
        
        # 添加所有新形状到画布并更新标签列表
        for shape in new_shapes:
            self.canvas.shapes.append(shape)
            self.add_label(shape)
        
        # 更新画布显示
        self.canvas.repaint()
        self.set_dirty()
        
        # 显示切割完成的提示信息
        QMessageBox.information(self, "切割完成", f"已将检测框切割为 {len(new_shapes)} 个小检测框")
    
    def _calculate_coverage_score(self, x1, y1, x2, y2, original_shape, sample_step=5):
        """计算一个矩形块对原始形状的覆盖得分"""
        overlap_pixels = 0
        total_pixels = 0
        
        for px in range(int(x1), int(x2), sample_step):
            for py in range(int(y1), int(y2), sample_step):
                total_pixels += 1
                if original_shape.contains_point(QPointF(px, py)):
                    overlap_pixels += 1
        
        # 计算中心点是否在原始形状内，这是一个额外的权重因素
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        center_in_shape = original_shape.contains_point(QPointF(center_x, center_y))
        
        # 基本覆盖率
        base_score = overlap_pixels / total_pixels if total_pixels > 0 else 0
        
        # 如果中心点在形状内，给一个额外的奖励，优先选择内部的块
        if center_in_shape:
            base_score = min(1.0, base_score * 1.2)
        
        return base_score


def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        reader = QImageReader(filename)
        reader.setAutoTransform(True)
        return reader.read()
    except:
        return default


def get_main_app(argv=None):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    if not argv:
        argv = []
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(new_icon("app"))
    # Tzutalin 201705+: Accept extra agruments to change predefined class file
    argparser = argparse.ArgumentParser()
    argparser.add_argument("image_dir", nargs="?")
    argparser.add_argument("class_file",
                           default=os.path.join(os.path.dirname(__file__), "data", "predefined_classes.txt"),
                           nargs="?")
    argparser.add_argument("save_dir", nargs="?")
    args = argparser.parse_args(argv[1:])

    args.image_dir = args.image_dir and os.path.normpath(args.image_dir)
    args.class_file = args.class_file and os.path.normpath(args.class_file)
    args.save_dir = args.save_dir and os.path.normpath(args.save_dir)
    
    # 如果没有指定class_file，使用默认的预设标签文件路径
    if not args.class_file:
        args.class_file = os.path.join(os.path.dirname(__file__), "data", "predefined_classes.txt")
        print(f"DEBUG: 使用默认的预设标签文件路径: {args.class_file}")

    # Usage : labelImg.py image classFile saveDir
    win = MainWindow(args.image_dir,
                     args.class_file,
                     args.save_dir)
    win.show()
    return app, win


def main():
    """construct main app and run it"""
    app, _win = get_main_app(sys.argv)
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
