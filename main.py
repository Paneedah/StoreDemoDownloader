import math
import os
import sys
import threading
from functools import partial

import win32api
import win32file
import shutil
import requests
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QWidget, QComboBox, QPushButton,
    QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QStackedWidget, QFrame, QGridLayout,
    QCheckBox, QSpacerItem, QSizePolicy, QScrollArea, QMessageBox, QProgressBar, QSlider
)
from PyQt5.QtCore import Qt, QSize, QTimer, QRunnable, pyqtSignal, QObject, pyqtSlot, QThreadPool
from PyQt5.QtGui import QIcon, QColor

class WorkerSignals(QObject):
    progress = pyqtSignal(float, float, str, QProgressBar)  # Updated to accept four arguments
    result = pyqtSignal(str)

class DownloadWorker(QRunnable):
    def __init__(self, url, file_path, file_name, signal, progress_bar):
        super(DownloadWorker, self).__init__()
        self.url = url
        self.file_path = file_path
        self.file_name = file_name
        self.signal = signal
        self.progress_bar = progress_bar  # Assign the progress bar

    @pyqtSlot()
    def run(self):
        """Thread worker for downloading files."""
        try:
            response = requests.get(self.url, stream=True)
            total_length = response.headers.get('content-length')

            if total_length is None:
                dl = len(response.content) / (1024 * 1024)
                total_mb = dl
                with open(self.file_path, 'wb') as f:
                    f.write(response.content)
                self.signal.progress.emit(dl, total_mb, self.file_name, self.progress_bar)
            else:
                dl = 0
                total_length = int(total_length)
                total_mb = total_length / (1024 * 1024)
                with open(self.file_path, 'wb') as f:
                    for data in response.iter_content(chunk_size=4096):
                        dl += len(data)
                        f.write(data)
                        downloaded_mb = dl / (1024 * 1024)
                        self.signal.progress.emit(downloaded_mb, total_mb, self.file_name, self.progress_bar)

            self.signal.result.emit(f"Finished downloading {self.file_name}")
        except Exception as e:
            self.signal.result.emit(f"Error downloading {self.file_name}: {e}")

def list_usb_devices():
    drives_info = []
    drive_bits = win32api.GetLogicalDrives()
    for drive_letter in range(26):
        mask = 1 << drive_letter
        if drive_bits & mask:
            drive = f"{chr(65 + drive_letter)}:\\"
            drive_type = win32file.GetDriveType(drive)
            if drive_type == win32file.DRIVE_REMOVABLE:
                try:
                    volume_info = win32api.GetVolumeInformation(drive)
                    usb_name = volume_info[0] if volume_info[0] else "Unnamed USB"
                    total, used, free = shutil.disk_usage(drive)
                    total_gb = total / (2**30)
                    free_gb = free / (2**30)
                    drive_info = f"{usb_name} ({drive}) - {free_gb:.2f} GB Free / {total_gb:.2f} GB Total"
                    drives_info.append((drive_info, free_gb, total_gb, drive))
                except Exception as e:
                    print(f"Error retrieving info for {drive}: {e}")
                    continue
    return drives_info


def fetch_data():
    url = 'https://raw.githubusercontent.com/Paneedah/StoreDemoDownloader/refs/heads/master/data.json'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        processed_data = {}
        for category_key in data:
            category_name = category_key.capitalize()
            items = data[category_key]
            processed_items = []
            for item in items:
                processed_item = {
                    "category": category_name,
                    "title": item.get("title", ""),
                    "duration": item.get("duration", ""),
                    "filetype": item.get("filetype", "").upper(),
                    "size": f"{item.get('size_gb', 0)}GB",
                    "size_gb": item.get("size_gb", 0),
                    "url": item.get("url", ""),
                }
                processed_items.append(processed_item)
            processed_data[category_name] = processed_items
        return processed_data
    else:
        print(f"Error fetching data: {response.status_code}")
        return {}


def update_progress(bar_index, downloaded_mb, total_mb, file_name, progress_bar):
    """Update the progress bar and show downloaded MB out of total MB."""
    percent_complete = (downloaded_mb / total_mb) * 100
    progress_bar.setValue(math.floor(percent_complete))
    progress_bar.setFormat(f"{file_name}: {downloaded_mb:.2f}MB / {total_mb:.2f}MB ({percent_complete:.2f}%)")


def log_result(message):
    """Log the result (finished or error)."""
    print(message)


class USBSelectorApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.completed_downloads = None
        self.active_downloads = None
        self.download_queue = None
        self.progress_bars = []

        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(3)

        monitorWidth = QApplication.desktop().screenGeometry().width()
        monitorHeight = QApplication.desktop().screenGeometry().height()
        wantedWidth = math.floor(monitorWidth * 0.75)
        wantedHeight = math.floor(monitorHeight * 0.75)

        self.selected_categories = []
        self.setWindowTitle("Demo Content Downloader")
        self.setGeometry(100, 100, wantedWidth, wantedHeight)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #23272A;
            }
            QListWidget {
                background-color: #2C2F33;
                color: #99AAB5;
                font-size: 16px;
                border: none;
            }
            QListWidget::item {
                padding: 15px;
            }
            QListWidget::item:selected {
                background-color: #2C2F33;
                color: #FFFFFF;
                border-left: 5px solid transparent;
                border-bottom: 3px solid #99AAB5;
            }
            QPushButton {
                background-color: #7289DA;
                color: white;
                font-size: 18px;
                padding: 12px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #677BC4;
            }
            QPushButton:pressed {
                background-color: #5B6EAE;
            }
            QLabel {
                font-size: 18px;
                color: #FFFFFF;
                margin-bottom: 10px;
            }
            QComboBox {
                background-color: #40444B;
                color: #FFFFFF;
                border: 1px solid #7289DA;
                padding: 8px;
                font-size: 16px;
                border-radius: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #40444B;
                color: #FFFFFF;
                selection-background-color: #7289DA;
            }
            QCheckBox {
                color: #FFFFFF;
                font-size: 16px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
            QFrame {
                background-color: #2C2F33;
                border-radius: 10px;
                padding: 15px;
            }
            QScrollArea {
                background-color: transparent;
            }
            QWidget#contentItem {
                background-color: #2C2F33;
            }
            QLineEdit {
                background-color: #40444B;
                color: #FFFFFF;
                border: 1px solid #7289DA;
                padding: 5px;
                font-size: 16px;
                border-radius: 5px;
            }
            QLabel#warningLabel {
                color: #FF5555;
                font-size: 16px;
            }
        """)

        # Main Layout
        main_layout = QHBoxLayout()

        # Sidebar for steps
        self.sidebar = QListWidget()
        self.sidebar.addItem(QListWidgetItem("1. Choose USB Drive"))
        self.sidebar.addItem(QListWidgetItem("2. Select Categories"))
        self.sidebar.addItem(QListWidgetItem("3. Select Content"))
        self.sidebar.addItem(QListWidgetItem("4. Confirm Download"))
        self.sidebar.addItem(QListWidgetItem("5. Downloading.."))
        self.sidebar.addItem(QListWidgetItem("6. Extracting.."))
        self.sidebar.addItem(QListWidgetItem("7. Finished!"))
        self.sidebar.setFixedWidth(225)
        self.sidebar.setFocusPolicy(Qt.NoFocus)
        self.sidebar.setSelectionMode(QListWidget.NoSelection)
        main_layout.addWidget(self.sidebar)

        # Stacked widget for the content
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Stage 1: USB Selection
        self.stage1_widget = QFrame()
        stage1_layout = QVBoxLayout()
        stage1_layout.setAlignment(Qt.AlignTop)
        self.stage1_label = QLabel("Select a USB Drive")
        stage1_layout.addWidget(self.stage1_label)

        self.comboBox = QComboBox(self)
        stage1_layout.addWidget(self.comboBox)

        self.concurrent_download_label = QLabel("Concurrent Downloads: 3")
        stage1_layout.addWidget(self.concurrent_download_label)

        self.concurrent_downloads = 3
        self.concurrent_download_slider = QSlider(Qt.Horizontal)
        self.concurrent_download_slider.setMinimum(1)
        self.concurrent_download_slider.setMaximum(15)
        self.concurrent_download_slider.setValue(3)
        self.concurrent_download_slider.setTickPosition(QSlider.TicksBelow)

        self.concurrent_download_slider.valueChanged.connect(self.update_concurrent_downloads)
        stage1_layout.addWidget(self.concurrent_download_slider)

        self.use_cache = QCheckBox("Use Cache (If this is enabled, the app will store downloaded files in a cache folder and use them instead of re-downloading)")
        self.use_cache.setChecked(True)
        self.use_cache.setStyleSheet("""
            QCheckBox {
                color: #FFFFFF;
                font-size: 16px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
        """)
        stage1_layout.addWidget(self.use_cache)

        stage1_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.refresh_button = QPushButton("Refresh USB List")
        self.refresh_button.clicked.connect(self.refresh_usb_list)
        stage1_layout.addWidget(self.refresh_button)

        self.stage1_continue = QPushButton("Continue")
        self.stage1_continue.clicked.connect(self.go_to_stage2)
        stage1_layout.addWidget(self.stage1_continue)

        self.stage1_widget.setLayout(stage1_layout)

        # Stage 2: Select Categories
        self.stage2_widget = QFrame()
        stage2_layout = QVBoxLayout()
        stage2_layout.setAlignment(Qt.AlignTop)

        self.stage2_label = QLabel("Select Categories")
        stage2_layout.addWidget(self.stage2_label)

        self.content_grid = QGridLayout()

        # Movies Checkbox
        self.movies_checkbox = QCheckBox(" Movies")
        self.movies_checkbox.setIcon(QIcon("icons/movies.svg"))
        self.movies_checkbox.setIconSize(QSize(32, 32))
        self.movies_checkbox.stateChanged.connect(self.update_checkbox_style)
        self.update_checkbox_style(self.movies_checkbox)

        # Music Checkbox
        self.music_checkbox = QCheckBox(" Music")
        self.music_checkbox.setIcon(QIcon("icons/music.svg"))
        self.music_checkbox.setIconSize(QSize(32, 32))
        self.music_checkbox.stateChanged.connect(self.update_checkbox_style)
        self.update_checkbox_style(self.music_checkbox)

        # Gaming Checkbox
        self.gaming_checkbox = QCheckBox(" Gaming")
        self.gaming_checkbox.setIcon(QIcon("icons/gaming.svg"))
        self.gaming_checkbox.setIconSize(QSize(32, 32))
        self.gaming_checkbox.stateChanged.connect(self.update_checkbox_style)
        self.update_checkbox_style(self.gaming_checkbox)

        self.content_grid.addWidget(self.movies_checkbox, 0, 0)
        self.content_grid.addWidget(self.music_checkbox, 0, 1)
        self.content_grid.addWidget(self.gaming_checkbox, 0, 2)

        stage2_layout.addLayout(self.content_grid)

        stage2_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        buttons_layout_stage2 = QHBoxLayout()
        self.stage2_back = QPushButton("Go Back")
        self.stage2_back.clicked.connect(self.go_to_stage1)
        buttons_layout_stage2.addWidget(self.stage2_back)

        self.stage2_continue = QPushButton("Continue")
        self.stage2_continue.clicked.connect(self.go_to_stage3)
        buttons_layout_stage2.addWidget(self.stage2_continue)

        stage2_layout.addLayout(buttons_layout_stage2)

        self.stage2_widget.setLayout(stage2_layout)

        # Stage 3: Select Content
        self.stage3_widget = QFrame()
        stage3_layout = QVBoxLayout()

        self.stage3_label = QLabel("Select Content")
        stage3_layout.addWidget(self.stage3_label)

        # Scroll Area for content items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollBar:vertical {
                background: #2C2F33;
                width: 16px;
                margin: 16px 0 16px 0;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #7289DA;
                min-height: 20px;
                border-radius: 8px;
            }
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
                background: none;
                height: 0px;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(content_widget)

        self.scroll_area.setWidget(content_widget)

        # Set stretch factor when adding scroll_area
        stage3_layout.addWidget(self.scroll_area, stretch=1)

        buttons_layout_stage3 = QHBoxLayout()
        self.stage3_back = QPushButton("Go Back")
        self.stage3_back.clicked.connect(self.go_to_stage2)
        buttons_layout_stage3.addWidget(self.stage3_back)

        self.stage3_continue = QPushButton("Continue")
        self.stage3_continue.clicked.connect(self.go_to_stage4)
        buttons_layout_stage3.addWidget(self.stage3_continue)

        stage3_layout.addLayout(buttons_layout_stage3)

        self.stage3_widget.setLayout(stage3_layout)

        # Stage 4: Confirm Download
        self.stage4_widget = QFrame()
        stage4_layout = QVBoxLayout()
        self.stage4_label = QLabel("Confirm Download")
        stage4_layout.addWidget(self.stage4_label)

        # Scroll Area for summary
        self.summary_scroll_area = QScrollArea()
        self.summary_scroll_area.setWidgetResizable(True)
        # Apply scrollbar styling
        self.summary_scroll_area.setStyleSheet("""
            QScrollBar:vertical {
                background: #2C2F33;
                width: 16px;
                margin: 16px 0 16px 0;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #7289DA;
                min-height: 20px;
                border-radius: 8px;
            }
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
                background: none;
                height: 0px;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        summary_content_widget = QWidget()
        summary_content_widget.setStyleSheet("background-color: transparent;")
        self.summary_layout = QVBoxLayout(summary_content_widget)
        self.summary_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_layout.setSpacing(2)
        self.summary_scroll_area.setWidget(summary_content_widget)
        stage4_layout.addWidget(self.summary_scroll_area, stretch=1)

        # Warning Label
        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warningLabel")
        stage4_layout.addWidget(self.warning_label)

        buttons_layout_stage4 = QHBoxLayout()
        self.stage4_back = QPushButton("Go Back")
        self.stage4_back.clicked.connect(self.go_to_stage3)
        buttons_layout_stage4.addWidget(self.stage4_back)

        self.stage4_continue = QPushButton("Confirm and Download")
        self.stage4_continue.clicked.connect(self.go_to_stage5)
        buttons_layout_stage4.addWidget(self.stage4_continue)

        stage4_layout.addLayout(buttons_layout_stage4)

        self.stage4_widget.setLayout(stage4_layout)

        # Stage 5: Downloading..
        self.stage5_widget = QFrame()
        stage5_layout = QVBoxLayout()
        stage5_layout.setAlignment(Qt.AlignCenter)
        self.stage5_label = QLabel("Downloading...")
        self.stage5_label.setStyleSheet("font-size: 24px; color: #FFFFFF;")
        stage5_layout.addWidget(self.stage5_label)
        self.stage5_widget.setLayout(stage5_layout)

        # Stage 6: Extracting.. (Placeholder)
        self.stage6_widget = QFrame()
        stage6_layout = QVBoxLayout()
        stage6_layout.setAlignment(Qt.AlignCenter)
        self.stage6_label = QLabel("Extracting...")
        self.stage6_label.setStyleSheet("font-size: 24px; color: #FFFFFF;")
        stage6_layout.addWidget(self.stage6_label)
        self.stage6_widget.setLayout(stage6_layout)

        # Stage 7: Finished!
        self.stage7_widget = QFrame()
        stage7_layout = QVBoxLayout()
        stage7_layout.setAlignment(Qt.AlignCenter)
        self.stage7_label = QLabel("Finished!")
        self.stage7_label.setStyleSheet("font-size: 24px; color: #FFFFFF;")
        stage7_layout.addWidget(self.stage7_label)
        self.stage7_widget.setLayout(stage7_layout)

        self.stacked_widget.addWidget(self.stage1_widget)
        self.stacked_widget.addWidget(self.stage2_widget)
        self.stacked_widget.addWidget(self.stage3_widget)
        self.stacked_widget.addWidget(self.stage4_widget)
        self.stacked_widget.addWidget(self.stage5_widget)
        self.stacked_widget.addWidget(self.stage6_widget)
        self.stacked_widget.addWidget(self.stage7_widget)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Initialize variables
        self.usb_devices = []
        self.selected_usb = None
        self.content_checkboxes = []
        self.selected_content_items = []
        self.data = None

        # Initialize stage 1 (USB selection)
        self.refresh_usb_list()
        self.go_to_stage1()

    def update_concurrent_downloads(self):
        """Update the number of concurrent downloads based on the slider value."""
        value = self.concurrent_download_slider.value()
        self.concurrent_download_label.setText(f"Concurrent Downloads: {value}")
        self.threadpool.setMaxThreadCount(value)
        self.concurrent_downloads = value

    def refresh_usb_list(self):
        """Refresh the list of USB devices."""
        self.comboBox.clear()
        usb_devices = list_usb_devices()
        self.usb_devices = usb_devices  # Store the list of USB devices
        if usb_devices:
            for usb in usb_devices:
                self.comboBox.addItem(usb[0])
        else:
            self.comboBox.addItem("No USB devices found")

    def go_to_stage1(self):
        """Go to stage 1 (USB selection)."""
        self.stage1_continue.setEnabled(False)

        self.stacked_widget.setCurrentIndex(0)
        self.highlight_sidebar_item(0)
        self.selected_usb = None

        self.data = fetch_data()
        if not self.data:
            QMessageBox.warning(self, "Error Fetching Data", "There was an error fetching the content data.")

            self.stage1_label.setText("Error: Could not fetch content data\n\nAre you connected to the internet?")
            self.stage1_label.setStyleSheet("color: #FF5555; font-size: 24px; margin-bottom: 20px;")

            self.sidebar.clear()
            self.sidebar.addItem(QListWidgetItem("1. ERROR"))

            self.stage1_continue.deleteLater()
            self.refresh_button.deleteLater()
            self.comboBox.deleteLater()
            return

        self.stage1_continue.setEnabled(True)

    def go_to_stage2(self):
        """Go to stage 2 (Select Categories)."""
        if self.comboBox.currentText() != "No USB devices found":
            index = self.comboBox.currentIndex()
            self.selected_usb = self.usb_devices[index]
            self.stacked_widget.setCurrentIndex(1)
            self.highlight_sidebar_item(1)

        else:
            QMessageBox.warning(self, "No USB Devices Found", "Please insert a USB drive and click 'Refresh USB List'.")
            self.refresh_usb_list()

    def go_to_stage3(self):
        """Go to stage 3 (Select Content)."""
        self.selected_categories = []
        if self.movies_checkbox.isChecked():
            self.selected_categories.append("Movies")
        if self.music_checkbox.isChecked():
            self.selected_categories.append("Music")
        if self.gaming_checkbox.isChecked():
            self.selected_categories.append("Gaming")

        if not self.selected_categories:
            # If no categories selected, show a message or prevent moving forward
            QMessageBox.warning(self, "No Categories Selected", "Please select at least one category.")
            return

        self.generate_content_items(self.selected_categories)
        self.stacked_widget.setCurrentIndex(2)
        self.highlight_sidebar_item(2)

    def go_to_stage4(self):
        """Go to stage 4 (Confirm Download)."""
        # Collect selected content items
        self.selected_content_items = []

        for checkbox, item in self.content_checkboxes:
            if checkbox.isChecked():
                self.selected_content_items.append(item)

        if not self.selected_content_items:
            QMessageBox.warning(self, "No Content Selected", "Please select at least one content item.")
            return

        self.generate_summary()
        self.stacked_widget.setCurrentIndex(3)
        self.highlight_sidebar_item(3)

    def go_to_stage5(self):
        """Go to stage 5 (Downloading)."""
        self.stacked_widget.setCurrentIndex(4)
        self.highlight_sidebar_item(4)

        # Clear cache and create necessary folders
        cache_folder = "cache"
        shutil.rmtree(cache_folder, ignore_errors=True)

        try:
            os.makedirs(cache_folder)
            os.mkdir(f"{cache_folder}/movies")
            os.mkdir(f"{cache_folder}/music")
            os.mkdir(f"{cache_folder}/gaming")
        except OSError as e:
            print(f"Error creating cache folder: {e}")
            return

        # Prepare download URLs
        download_urls = [(f"https://cdn.skyy.cc/{item['url']}", f"{cache_folder}/{item['category']}/{item['title']}.mp4", item['title']) for item in self.selected_content_items]

        self.start_downloads(download_urls)

    def start_downloads(self, download_urls):
        """Start downloading files using QThreadPool and show progress."""
        self.download_queue = download_urls
        self.active_downloads = []
        self.completed_downloads = 0

        # Start up to 3 downloads initially (one for each progress bar)
        for i in range(min(self.concurrent_downloads, len(download_urls))):
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setAlignment(Qt.AlignCenter)
            progress_bar.setStyleSheet("""
                                       QProgressBar {
                                           background-color: #7289DA;
                                           border-radius: 10px;
                                           text-align: center;
                                       }
                                       QProgressBar::chunk {
                                           background-color: #57f1bf;
                                           border-radius: 10px;
                                       }
                                   """)
            self.progress_bars.append(progress_bar)
            self.stage5_widget.layout().addWidget(progress_bar)
            self.stage5_widget.layout().setSpacing(10)
            self.start_next_download(i)

    def start_next_download(self, bar_index):
        """Start the next download from the queue, if available."""
        if not self.download_queue:
            return  # No more downloads to start

        # Get the next download in the queue
        url, file_path, file_name = self.download_queue.pop(0)
        worker_signals = WorkerSignals()
        worker_signals.progress.connect(partial(update_progress, bar_index))
        worker_signals.result.connect(partial(self.on_download_complete, bar_index))

        # Pass the progress bar directly to the worker
        download_worker = DownloadWorker(url, file_path, file_name, worker_signals, self.progress_bars[bar_index])
        self.active_downloads.append(download_worker)
        self.threadpool.start(download_worker)

    def on_download_complete(self, bar_index, message):
        """Handle download completion, start the next download if any are left."""
        print(message)  # Log the result (e.g., "Finished downloading X")

        # Start the next download on the freed-up progress bar
        self.start_next_download(bar_index)

        # Check if all downloads are completed
        self.completed_downloads += 1
        if self.completed_downloads == len(self.selected_content_items):
            self.go_to_stage6()  # Move to the next stage after all downloads are done

    def go_to_stage6(self):
        """Go to stage 6 (Extracting)."""
        self.stacked_widget.setCurrentIndex(5)
        self.highlight_sidebar_item(5)
        # Placeholder: Simulate extracting
        QTimer.singleShot(2000, self.go_to_stage7)

    def go_to_stage7(self):
        """Go to stage 7 (Finished)."""
        self.stacked_widget.setCurrentIndex(6)
        self.highlight_sidebar_item(6)

    def highlight_sidebar_item(self, index):
        """Highlight the current item in the sidebar."""
        for i in range(self.sidebar.count()):
            item = self.sidebar.item(i)
            if i == index:
                item.setBackground(QColor("#2C2F33"))
                item.setForeground(QColor("#FFFFFF"))
                item.setSelected(True)
            else:
                item.setBackground(QColor("#2C2F33"))
                item.setForeground(QColor("#99AAB5"))
                item.setSelected(False)

    def update_checkbox_style(self, checkbox):
        """Update the style of the checkbox based on its state."""
        if isinstance(checkbox, int):
            checkbox = self.sender()
        if checkbox.isChecked():
            checkbox.setStyleSheet("""
                QCheckBox {
                    background-color: #3A3D41;
                    border-radius: 5px;
                    color: #FFFFFF;
                    font-size: 16px;
                    padding: 10px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                }
            """)
        else:
            checkbox.setStyleSheet("""
                QCheckBox {
                    background-color: transparent;
                    color: #FFFFFF;
                    font-size: 16px;
                    padding: 10px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                }
            """)

    def generate_content_items(self, categories):
        """Generate sample content items based on selected categories."""

        for i in reversed(range(self.content_layout.count())):
            widget = self.content_layout.takeAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        self.content_checkboxes = []
        self.content_layout.setAlignment(Qt.AlignTop)

        for category in categories:
            print(f"Generating content for {category}")

            # Add category heading
            category_label = QLabel(f"{category}")
            category_label.setStyleSheet("color: #57f1bf; font-size: 20px;")
            self.content_layout.addWidget(category_label)

            # Header row
            header_widget = QWidget()
            header_layout = QHBoxLayout()
            header_widget.setLayout(header_layout)
            header_widget.setStyleSheet("background-color: #2C2F33;")

            title_header = QLabel("Title")
            title_header.setStyleSheet("color: #99AAB5; font-size: 14px;")
            title_header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            header_layout.addWidget(title_header)

            duration_header = QLabel("Duration")
            duration_header.setStyleSheet("color: #99AAB5; font-size: 14px;")
            duration_header.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            header_layout.addWidget(duration_header)

            filetype_header = QLabel("File Type")
            filetype_header.setStyleSheet("color: #99AAB5; font-size: 14px;")
            filetype_header.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            header_layout.addWidget(filetype_header)

            size_header = QLabel("Size")
            size_header.setStyleSheet("color: #99AAB5; font-size: 14px;")
            size_header.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            header_layout.addWidget(size_header)

            header_layout.addStretch()
            self.content_layout.addWidget(header_widget)

            items = self.data.get(category, [])
            for item in items:
                content_item = QWidget()
                content_item.setObjectName("contentItem")
                content_item.setStyleSheet("background-color: #2C2F33;")
                item_layout = QHBoxLayout()
                item_layout.setContentsMargins(0, 0, 0, 0)
                content_item.setLayout(item_layout)
                content_item.setFixedHeight(60)

                checkbox = QCheckBox()
                checkbox.setChecked(True)
                checkbox.setStyleSheet("""
                    QCheckBox {
                        color: #FFFFFF;
                    }
                    QCheckBox::indicator {
                        width: 20px;
                        height: 20px;
                    }
                """)

                self.content_checkboxes.append((checkbox, item))

                title_label = QLabel(item["title"])
                title_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
                title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

                duration_label = QLabel(item["duration"])
                duration_label.setStyleSheet("color: #99AAB5; font-size: 14px;")
                duration_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

                filetype_label = QLabel(item["filetype"])
                filetype_label.setStyleSheet("color: #99AAB5; font-size: 14px;")
                filetype_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

                size_label = QLabel(item["size"])
                size_label.setStyleSheet("color: #99AAB5; font-size: 14px;")
                size_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

                item_layout.addWidget(checkbox)
                item_layout.addWidget(title_label)
                item_layout.addWidget(duration_label)
                item_layout.addWidget(filetype_label)
                item_layout.addWidget(size_label)
                item_layout.addStretch()

                self.content_layout.addWidget(content_item)

    def generate_summary(self):
        """Generate the summary in Stage 4."""
        for i in reversed(range(self.summary_layout.count())):
            widget = self.summary_layout.takeAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        total_size = 0.0
        content_per_category = {}

        for item in self.selected_content_items:
            category = item.get("category")
            title = item["title"]
            size = item["size"]
            size_gb = item["size_gb"]
            total_size += size_gb

            if category not in content_per_category:
                content_per_category[category] = []

            content_per_category[category].append(f"{title} ({size})")

        content_desc = ""

        for category, items in content_per_category.items():
            content_desc += f"\n\n{category}:\n"
            for item in items:
                content_desc += f"  - {item}\n"

        summary_label = QLabel(f"{content_desc}")
        summary_label.setStyleSheet("color: #FFFFFF; font-size: 16px;")
        self.summary_layout.setAlignment(Qt.AlignTop)
        self.summary_layout.addWidget(summary_label)

        usb_free_space = self.selected_usb[1]

        if total_size > usb_free_space:
            self.warning_label.setText("Warning: Not enough space on the selected USB drive!")
            self.stage4_continue.setEnabled(False)
        else:
            self.warning_label.setText(f"Total Required Space: {total_size:.2f} GB / {usb_free_space:.2f} GB Free")
            self.stage4_continue.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    thread = threading.Thread(target=app.exec_)

    window = USBSelectorApp()
    window.show()

    sys.exit(app.exec_())
