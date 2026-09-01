"""
Download Table Model for displaying downloads in the GUI
"""
import os
from typing import List
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionProgressBar
from .download_item import DownloadItem


class DownloadTableModel(QAbstractTableModel):
    COLUMNS = ["Action", "File Name", "Size", "Progress", "Speed", "Time Left", "Status"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.downloads: List[DownloadItem] = []
        self._progress_info = {}

    def rowCount(self, parent=QModelIndex()):
        return len(self.downloads)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        dl = self.downloads[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 1:
                return os.path.basename(dl.save_path)
            elif col == 2:
                if dl.total_bytes > 0:
                    return f"{dl.downloaded_bytes / (1024*1024):.1f} / {dl.total_bytes / (1024*1024):.1f} MB"
                else:
                    return f"{dl.downloaded_bytes / (1024*1024):.1f} MB"
            elif col == 4:
                if dl.status == DownloadItem.STATUS_DOWNLOADING:
                    speed_kb = dl.get_speed_kbps()
                    if speed_kb > 1024:
                        return f"{speed_kb/1024:.1f} MB/s"
                    else:
                        return f"{speed_kb:.1f} KB/s"
                return ""
            elif col == 5:
                if dl.status == DownloadItem.STATUS_DOWNLOADING:
                    eta = self._progress_info.get(row, (-1, -1))[1]
                    if eta >= 0:
                        mins, sec = divmod(eta, 60)
                        if mins > 0:
                            return f"{mins}m {sec}s"
                        else:
                            return f"{sec}s"
                return ""
            elif col == 6:
                return dl.status
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (2, 4, 5):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        elif role == Qt.ItemDataRole.UserRole:
            if col == 3:
                return self._progress_info.get(row, (-1, -1))[0]
            elif col == 5:
                return self._progress_info.get(row, (-1, -1))[1]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def add_download(self, dl: DownloadItem):
        row = len(self.downloads)
        self.beginInsertRows(QModelIndex(), row, row)
        self.downloads.append(dl)
        self._progress_info[row] = (-1, -1)
        self.endInsertRows()
        dl.progressChanged.connect(lambda *args, r=row: self._update_progress(r, *args))
        dl.statusChanged.connect(lambda status, r=row: self._update_status(r, status))
        dl.finished.connect(lambda dl: self._on_download_finished(dl))

    def remove_download(self, row: int):
        if row < 0 or row >= len(self.downloads):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        dl = self.downloads.pop(row)
        if row in self._progress_info:
            del self._progress_info[row]
        self.endRemoveRows()
        dl.remove()

    def _update_progress(self, row, downloaded, total, percent, speed, eta):
        if row >= len(self.downloads):
            return
        self._progress_info[row] = (percent, eta)
        top_left = self.index(row, 2)
        bottom_right = self.index(row, 5)
        self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole])

    def _update_status(self, row, status):
        if row >= len(self.downloads):
            return
        idx = self.index(row, 6)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])

    def _on_download_finished(self, dl):
        # This is called when a download finishes; we don't need to do anything here,
        # but we can trigger a UI update if necessary.
        pass

    def get_download(self, row):
        if 0 <= row < len(self.downloads):
            return self.downloads[row]
        return None

    def get_row(self, dl):
        try:
            return self.downloads.index(dl)
        except ValueError:
            return -1


class ProgressBarDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() == 3:
            percent = index.data(Qt.ItemDataRole.UserRole)
            if percent is not None and isinstance(percent, int) and percent >= 0:
                progress = QStyleOptionProgressBar()
                progress.rect = option.rect
                progress.minimum = 0
                progress.maximum = 100
                progress.progress = percent
                progress.text = f"{percent}%"
                progress.textVisible = True
                QApplication.style().drawControl(QStyle.ControlElement.CE_ProgressBar, progress, painter)
            else:
                painter.save()
                painter.setPen(QColor("#cccccc"))
                painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "—")
                painter.restore()
        else:
            super().paint(painter, option, index)
