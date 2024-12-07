import os
import sys
import json
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QPushButton, QLabel,
                             QFileDialog, QTextEdit, QMessageBox, QComboBox,
                             QTableWidget, QTableWidgetItem, QTabWidget,
                             QCheckBox, QProgressBar, QGroupBox, QHeaderView,
                             QToolTip)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QColor, QCursor


class RenameWorker(QThread):
    """后台重命名处理线程"""
    progress = pyqtSignal(str)  # 进度信号
    progress_value = pyqtSignal(int)  # 进度条信号
    preview_ready = pyqtSignal(list)  # 预览信号
    finished = pyqtSignal(int)  # 完成信号

    def __init__(self, directory, old_suffix, new_suffix, operation_mode, preview_only=False, show_new_name=True):
        super().__init__()
        self.directory = directory
        self.old_suffix = old_suffix.strip()
        self.new_suffix = new_suffix.strip()
        self.operation_mode = operation_mode
        self.preview_only = preview_only
        self.show_new_name = show_new_name
        self.is_running = True

    def quit(self):
        """停止线程"""
        self.is_running = False
        super().quit()

    def run(self):
        try:
            # 确保后缀格式正确
            if self.old_suffix and not self.old_suffix.startswith('.'):
                self.old_suffix = '.' + self.old_suffix
            if self.operation_mode == "replace" and self.new_suffix and not self.new_suffix.startswith('.'):
                self.new_suffix = '.' + self.new_suffix

            # 获取所有匹配的文件
            target_files = [f for f in os.listdir(self.directory)
                            if f.lower().endswith(self.old_suffix.lower())]

            if not target_files:
                self.progress.emit(f"未找到后缀为 {self.old_suffix} 的文件")
                self.finished.emit(0)
                return

            # 预览模式
            if self.preview_only:
                preview_data = []
                for file in target_files:
                    if not self.is_running:
                        return

                    old_name = file
                    if not self.show_new_name:
                        # 只显示原文件名，新文件���留空
                        new_name = ""
                        status = "等待输入新后缀"
                    else:
                        if self.operation_mode == "remove":
                            new_name = file[:-len(self.old_suffix)]
                        else:  # replace
                            new_name = file[:-len(self.old_suffix)
                                            ] + self.new_suffix

                        status = "可以处理"
                        if os.path.exists(os.path.join(self.directory, new_name)):
                            status = "文件已存在"

                    preview_data.append((old_name, new_name, status))

                if self.is_running:
                    self.preview_ready.emit(preview_data)
                return

            # 实际处理文件
            success_count = 0
            total_files = len(target_files)

            for index, file in enumerate(target_files):
                if not self.is_running:
                    break

                old_path = os.path.join(self.directory, file)

                if self.operation_mode == "remove":
                    new_name = file[:-len(self.old_suffix)]
                else:  # replace
                    new_name = file[:-len(self.old_suffix)] + self.new_suffix

                new_path = os.path.join(self.directory, new_name)

                try:
                    if os.path.exists(new_path):
                        self.progress.emit(f"警告: '{new_name}' 已存在，跳过")
                        continue

                    os.rename(old_path, new_path)
                    success_count += 1
                    self.progress.emit(f"成功: {file} -> {new_name}")

                except Exception as e:
                    self.progress.emit(f"错误: 无法重命名 '{file}': {str(e)}")

                # 更新进度条
                if self.is_running:
                    progress = int((index + 1) / total_files * 100)
                    self.progress_value.emit(progress)

            # 保存操作记录
            if self.is_running:
                self.save_history(success_count, total_files)
                self.finished.emit(success_count)

        except Exception as e:
            if self.is_running:
                self.progress.emit(f"发生错误: {str(e)}")
                self.finished.emit(0)

    def save_history(self, success_count, total_files):
        """保存操作历史"""
        history_file = os.path.join(
            os.path.dirname(__file__), "rename_history.json")
        history_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "directory": self.directory,
            "old_suffix": self.old_suffix,
            "new_suffix": self.new_suffix if self.operation_mode == "replace" else "",
            "operation": self.operation_mode,
            "success_count": success_count,
            "total_files": total_files
        }

        try:
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            else:
                history = []

            history.insert(0, history_entry)  # 新记录插入到最前面
            # 只保留最近50条记录
            history = history[:50]

            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存历史记录失败: {str(e)}")


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.initUI()
        self.load_last_directory()
        # 初始化工作线程变量
        self.worker = None
        self.preview_worker = None
        # 保存标签页引用
        self.tab_widget = None

    def closeEvent(self, event):
        """���口关闭事件处理"""
        # 确保所有线程都已经停止
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        if self.preview_worker and self.preview_worker.isRunning():
            self.preview_worker.quit()
            self.preview_worker.wait()
        event.accept()

    def initUI(self):
        self.setWindowTitle('文件后缀处理工具')
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        # 创建中央部件和主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 创建选项卡
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # 主操作页面
        main_tab = QWidget()
        self.tab_widget.addTab(main_tab, "文件处理")

        # 历史记录页面
        history_tab = QWidget()
        self.tab_widget.addTab(history_tab, "操作历史")

        # 设置主操作页面
        self.setup_main_tab(main_tab)

        # 设置历史记录页面
        self.setup_history_tab(history_tab)

    def setup_main_tab(self, tab):
        """设置主操作页面"""
        layout = QVBoxLayout(tab)

        # 文件夹选择区域
        folder_group = QGroupBox("文件夹选择")
        folder_layout = QHBoxLayout()
        folder_group.setLayout(folder_layout)

        path_label = QLabel("目标文件夹:")
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText('请选择或输入文件夹路径...')
        self.path_input.textChanged.connect(self.refresh_preview)
        browse_btn = QPushButton('浏览...')
        browse_btn.clicked.connect(self.browse_folder)

        folder_layout.addWidget(path_label)
        folder_layout.addWidget(self.path_input)
        folder_layout.addWidget(browse_btn)
        layout.addWidget(folder_group)

        # 后缀设置区域
        suffix_group = QGroupBox("后缀设置")
        suffix_layout = QVBoxLayout()
        suffix_group.setLayout(suffix_layout)

        # 原后缀输入区域
        old_suffix_layout = QHBoxLayout()
        old_suffix_label = QLabel("原后缀:")
        self.old_suffix_input = QLineEdit()
        self.old_suffix_input.setPlaceholderText('例如: .pdf')
        self.old_suffix_input.textChanged.connect(self.refresh_preview)
        old_suffix_layout.addWidget(old_suffix_label)
        old_suffix_layout.addWidget(self.old_suffix_input)
        suffix_layout.addLayout(old_suffix_layout)

        # 操作模式选择区域
        operation_layout = QHBoxLayout()
        operation_label = QLabel("处理方式:")
        self.operation_mode = QComboBox()
        self.operation_mode.addItems(["替换后缀", "移除后缀"])  # 改变顺序，使替换后缀为默认选项
        self.operation_mode.currentTextChanged.connect(self.on_mode_changed)
        operation_layout.addWidget(operation_label)
        operation_layout.addWidget(self.operation_mode)
        operation_layout.addStretch()
        suffix_layout.addLayout(operation_layout)

        # 新后缀输入区域
        self.new_suffix_container = QWidget()
        new_suffix_layout = QHBoxLayout()
        self.new_suffix_container.setLayout(new_suffix_layout)
        self.new_suffix_label = QLabel("新后缀:")
        self.new_suffix_input = QLineEdit()
        self.new_suffix_input.setPlaceholderText('例如: .txt')
        self.new_suffix_input.textChanged.connect(self.refresh_preview)
        new_suffix_layout.addWidget(self.new_suffix_label)
        new_suffix_layout.addWidget(self.new_suffix_input)
        suffix_layout.addWidget(self.new_suffix_container)

        layout.addWidget(suffix_group)

        # 选项设置
        options_group = QGroupBox("选项")
        options_layout = QHBoxLayout()
        options_group.setLayout(options_layout)

        self.backup_checkbox = QCheckBox("处理前创建备份")
        self.backup_checkbox.setChecked(True)
        options_layout.addWidget(self.backup_checkbox)

        self.case_sensitive_checkbox = QCheckBox("区分大小写")
        options_layout.addWidget(self.case_sensitive_checkbox)

        layout.addWidget(options_group)

        # 预览表格
        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout()
        preview_group.setLayout(preview_layout)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)  # 减少一列，移除序号列
        self.preview_table.setHorizontalHeaderLabels(["原文件名", "新文件名", "状态"])

        # 设置表格属性
        self.preview_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)  # 原文件名自适应
        self.preview_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)  # 新文件名自适应
        self.preview_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Fixed)  # 状态列固定宽度
        self.preview_table.setColumnWidth(2, 100)  # 设置状态列宽度

        # 显示行号
        self.preview_table.verticalHeader().setVisible(True)
        self.preview_table.verticalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignCenter)

        # 设置工具提示
        self.preview_table.setMouseTracking(True)
        self.preview_table.cellEntered.connect(self.show_full_filename)

        preview_layout.addWidget(self.preview_table)
        layout.addWidget(preview_group)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 操作按钮
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton('开始处理')
        self.start_btn.clicked.connect(self.start_processing)
        button_layout.addWidget(self.start_btn)
        layout.addLayout(button_layout)

        # 日志显示
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()
        log_group.setLayout(log_layout)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        layout.addWidget(log_group)

    def setup_history_tab(self, tab):
        """设置历史记录页面"""
        layout = QVBoxLayout(tab)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels([
            "时间", "文件夹", "原后缀", "新后缀", "操作", "处理结果"
        ])

        # 设置表格属性
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)  # 时间列自适应内容
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)  # 文件夹列拉伸
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)  # 原后缀列自适应内容
        header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)  # 新后缀列自适应内容
        header.setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents)  # 操作列自适应内容
        header.setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents)  # 处理结果列自适应内容

        layout.addWidget(self.history_table)

        # 添加清空历史按钮
        button_layout = QHBoxLayout()

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_history)
        button_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("清空历史")
        clear_btn.clicked.connect(self.clear_history)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4444;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #ff6666;
            }
            QPushButton:pressed {
                background-color: #cc0000;
            }
        """)
        button_layout.addWidget(clear_btn)

        layout.addLayout(button_layout)

        # 加载历史记录
        self.load_history()

    def load_history(self):
        """加载历史记录"""
        history_file = os.path.join(
            os.path.dirname(__file__), "rename_history.json")
        try:
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)

                self.history_table.setRowCount(len(history))
                for row, entry in enumerate(history):
                    # 设置时间
                    time_item = QTableWidgetItem(entry["timestamp"])
                    time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.history_table.setItem(row, 0, time_item)

                    # 设置文件夹
                    dir_item = QTableWidgetItem(entry["directory"])
                    self.history_table.setItem(row, 1, dir_item)

                    # 设置原后缀
                    old_suffix_item = QTableWidgetItem(entry["old_suffix"])
                    old_suffix_item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter)
                    self.history_table.setItem(row, 2, old_suffix_item)

                    # 设置新后缀
                    new_suffix_item = QTableWidgetItem(entry["new_suffix"])
                    new_suffix_item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter)
                    self.history_table.setItem(row, 3, new_suffix_item)

                    # 设置操作
                    operation_item = QTableWidgetItem(entry["operation"])
                    operation_item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter)
                    self.history_table.setItem(row, 4, operation_item)

                    # 设置处理结果
                    result = f"{entry['success_count']}/{entry['total_files']} 成功"
                    result_item = QTableWidgetItem(result)
                    result_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.history_table.setItem(row, 5, result_item)

        except Exception as e:
            QMessageBox.warning(self, "警告", f"加载历史记录失败: {str(e)}")

    def clear_history(self):
        """清空历史记录"""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有历史记录吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            history_file = os.path.join(
                os.path.dirname(__file__), "rename_history.json")
            try:
                if os.path.exists(history_file):
                    os.remove(history_file)
                self.history_table.setRowCount(0)
                QMessageBox.information(self, "成功", "历史记录已清空")
            except Exception as e:
                QMessageBox.warning(self, "警告", f"清空历史记录失败: {str(e)}")

    def load_last_directory(self):
        """加载上次使用的目录"""
        history_file = os.path.join(
            os.path.dirname(__file__), "rename_history.json")
        try:
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                if history:
                    last_dir = history[0]["directory"]
                    if os.path.exists(last_dir):
                        self.path_input.setText(last_dir)
        except Exception:
            pass

    def on_mode_changed(self, text):
        """处理操作模式改变"""
        # 根据模式显示/隐藏新后缀输入框
        is_replace_mode = text == "替换后缀"
        self.new_suffix_container.setVisible(is_replace_mode)

        # 更新新后缀输入框的提示文本
        if is_replace_mode:
            self.new_suffix_input.setPlaceholderText('例如: .txt')

        # 清空新后缀输入
        if not is_replace_mode:
            self.new_suffix_input.clear()

        # 刷新预览
        self.refresh_preview()

    def browse_folder(self):
        """打开文件夹选择对话框"""
        current_dir = self.path_input.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择文件夹",
            current_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.path_input.setText(folder)
            # 自动预览会通过 path_input 的 textChanged 信号触发

    def refresh_preview(self):
        """自动刷新预览"""
        # 如果没有选择目录或没有输入原后缀，不进行预览
        if not self.path_input.text().strip() or not self.old_suffix_input.text().strip():
            self.preview_table.setRowCount(0)
            return

        # 在替换模式下，不需要等待新后缀就可以预览
        mode = self.operation_mode.currentText()
        if mode == "替换后缀" and not self.new_suffix_input.text().strip():
            # 显示原文件，新文件名暂时保持为空
            self.preview_changes(show_new_name=False)
        else:
            # 正常预览
            self.preview_changes(show_new_name=True)

    def preview_changes(self, show_new_name=True):
        """预览变更"""
        self.preview_table.setRowCount(0)
        self.log_display.clear()
        self.progress_bar.setVisible(False)

        # 如果存在正在运行的预览线程，先停止它
        if self.preview_worker and self.preview_worker.isRunning():
            self.preview_worker.quit()
            self.preview_worker.wait()

        # 创建预览线程
        operation_mode = "remove" if self.operation_mode.currentText() == "移除后缀" else "replace"
        self.preview_worker = RenameWorker(
            self.path_input.text().strip(),
            self.old_suffix_input.text().strip(),
            self.new_suffix_input.text().strip(),
            operation_mode,
            preview_only=True,
            show_new_name=show_new_name
        )

        self.preview_worker.preview_ready.connect(self.update_preview_table)
        self.preview_worker.start()

    def update_preview_table(self, preview_data):
        """更新预览表格"""
        # 按文件名排序
        preview_data.sort(key=lambda x: x[0].lower())

        # 计算总行数
        total_rows = len(preview_data)
        self.preview_table.setRowCount(total_rows)

        # 用于存储相似文本组
        similar_texts = {}

        # 查找相似文本
        for i, (old_name, new_name, status) in enumerate(preview_data):
            # 移除后缀后的文件名
            name_without_ext = os.path.splitext(old_name)[0]

            # 查找最长的相似前缀
            for existing_name in similar_texts.keys():
                # 计算两个文本的最长公共前缀
                common_prefix = os.path.commonprefix(
                    [existing_name.lower(), name_without_ext.lower()])
                if len(common_prefix) >= 3:  # 至少3个字符相同才认为相似
                    similar_texts[existing_name].append(i)
                    break
            else:
                similar_texts[name_without_ext] = [i]

        # 为相似文本分配颜色
        colors = [
            QColor(255, 230, 230),  # 浅红色
            QColor(230, 255, 230),  # 浅绿色
            QColor(230, 230, 255),  # 浅蓝色
            QColor(255, 255, 230),  # 浅黄色
            QColor(255, 230, 255),  # 浅紫色
            QColor(230, 255, 255),  # 浅青色
        ]
        color_index = 0
        similar_groups = {i: None for i in range(total_rows)}

        # 只为有多个文件的组分配颜色
        for indices in similar_texts.values():
            if len(indices) > 1:
                for idx in indices:
                    similar_groups[idx] = colors[color_index]
                color_index = (color_index + 1) % len(colors)

        for row, (old_name, new_name, status) in enumerate(preview_data):
            # 原文件名列
            old_name_items = self.create_filename_item(old_name)
            if len(old_name_items) == 2:  # 如果有后缀
                self.preview_table.setSpan(row, 0, 1, 1)  # 合并单元格
                self.preview_table.setItem(row, 0, old_name_items[0])
                old_name_items[0].setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                # 将后缀添加到同一个单元格
                old_text = old_name_items[0].text()
                ext_text = old_name_items[1].text()
                old_name_items[0].setText(f"{old_text}{ext_text}")
                old_name_items[0].setForeground(QColor(0, 0, 0))  # 黑色
            else:
                self.preview_table.setItem(row, 0, old_name_items[0])

            # 新文件名列
            new_name_items = self.create_filename_item(new_name)
            if len(new_name_items) == 2:  # 如果有后缀
                self.preview_table.setSpan(row, 1, 1, 1)  # 合并单元格
                self.preview_table.setItem(row, 1, new_name_items[0])
                new_name_items[0].setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                # 将后缀添加到同一个单元格
                new_text = new_name_items[0].text()
                ext_text = new_name_items[1].text()
                new_name_items[0].setText(f"{new_text}{ext_text}")
                new_name_items[0].setForeground(QColor(0, 0, 0))  # 黑色
            else:
                self.preview_table.setItem(row, 1, new_name_items[0])

            # 状态列
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "可以处理":
                status_item.setForeground(QColor(60, 179, 113))  # 绿色
            elif status == "等待输入新后缀":
                status_item.setForeground(QColor(70, 130, 180))  # 钢青色
            else:
                status_item.setForeground(QColor(255, 69, 0))  # ��色
            self.preview_table.setItem(row, 2, status_item)

            # 设置行背景色
            if similar_groups[row] is not None:
                for col in range(3):
                    item = self.preview_table.item(row, col)
                    if item:
                        item.setBackground(similar_groups[row])
                        # 为相似文本设置加粗字体
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)

        self.preview_table.resizeRowsToContents()

    def create_filename_item(self, filename):
        """创建文件名单元格项"""
        # 分离文件名和后缀
        name, ext = os.path.splitext(
            filename) if '.' in filename else (filename, '')

        # 如果文件名过长，进行缩略
        max_length = 30
        if len(name) > max_length:
            display_name = name[:max_length//2] + '...' + name[-max_length//2:]
            if ext:
                display_name += ext
        else:
            display_name = filename

        # 创建表格项
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, filename)  # 存储完整文件名用于工具提示
        item.setText(display_name)  # 设置显示文本

        # ���果有后缀，设置后缀灰色
        if ext:
            # 创建自定义颜色的文本
            name_part = display_name[:-len(ext)]
            ext_part = ext
            item.setText(name_part)  # 设置主文件名

            # 设置后缀为灰色
            ext_item = QTableWidgetItem(ext_part)
            ext_item.setForeground(QColor(128, 128, 128))  # 灰色
            return [item, ext_item]

        return [item]

    def show_full_filename(self, row, column):
        """显示完整文件名的工具提示"""
        if column in [0, 1]:  # 只在文件名列显示工具提示
            item = self.preview_table.item(row, column)
            if item and item.data(Qt.ItemDataRole.UserRole):  # 使用UserRole存储完整文件名
                QToolTip.showText(QCursor.pos(), item.data(
                    Qt.ItemDataRole.UserRole))
            else:
                QToolTip.hideText()

    def validate_inputs(self):
        """验证输入"""
        directory = self.path_input.text().strip()
        old_suffix = self.old_suffix_input.text().strip()
        new_suffix = self.new_suffix_input.text().strip()
        operation_mode = self.operation_mode.currentText()

        if not directory:
            QMessageBox.warning(self, "警告", "请选择要处理的文件夹!")
            return False

        if not os.path.exists(directory):
            QMessageBox.warning(self, "警告", "所选文件夹不存在!")
            return False

        if not old_suffix:
            QMessageBox.warning(self, "警告", "请输入要处理的文件后缀!")
            return False

        if operation_mode == "替换后缀" and not new_suffix:
            QMessageBox.warning(self, "警告", "请输入新的文件后缀!")
            return False

        return True

    def start_processing(self):
        """开始处理文件"""
        if not self.validate_inputs():
            return

        # 如果选择了备份，先创建备份
        if self.backup_checkbox.isChecked():
            self.create_backup()

        # 清空日志显示
        self.log_display.clear()

        # 显示并重置进度条
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # 禁用按钮,防止重复操作
        self.start_btn.setEnabled(False)
        self.statusBar().showMessage('处理中...')

        # 获取操作模式
        operation_mode = "remove" if self.operation_mode.currentText() == "移除后缀" else "replace"

        # 如存在正在运行的线程，先停止它
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()

        # 创建并启动工作线程
        self.worker = RenameWorker(
            self.path_input.text().strip(),
            self.old_suffix_input.text().strip(),
            self.new_suffix_input.text().strip(),
            operation_mode
        )
        self.worker.progress.connect(self.update_log)
        self.worker.progress_value.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.process_finished)
        self.worker.start()

    def create_backup(self):
        """创建备份"""
        try:
            source_dir = self.path_input.text().strip()
            backup_dir = source_dir + "_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")

            # 复制整个目录
            import shutil
            shutil.copytree(source_dir, backup_dir)

            self.update_log(f"已创建备份: {backup_dir}")
        except Exception as e:
            QMessageBox.warning(self, "警告", f"创建备份失败: {str(e)}")

    def update_log(self, message):
        """更新日志显示"""
        self.log_display.append(message)

    def process_finished(self, success_count):
        """处理完成的回调"""
        self.start_btn.setEnabled(True)
        self.statusBar().showMessage(f'完成! 成功处理 {success_count} 个文件')

        # 刷新历史记录
        self.load_history()

        QMessageBox.information(
            self,
            "完成",
            f"处理完成!\n成功处理 {success_count} 个文件"
        )


def main():
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
