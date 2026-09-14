"""
Custom Table View widget
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableView


class CustomTableView(QTableView):
    """Custom Table View: clears selection when clicking on empty area"""
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if self.viewport().rect().contains(pos):
                index = self.indexAt(pos)
                if not index.isValid():
                    self.clearSelection()
        super().mousePressEvent(event)
