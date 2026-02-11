import logging
from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt


class VideoWidget(QLabel):
    """Display a RGB frame in a QLabel widget"""

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: black; color: white;")
        self.setText("Ready for streaming...")
        self.setMinimumSize(640, 480)
        self.pixmap = None
        self.frame_width = 0
        self.frame_height = 0

    def draw(self):
        if (self.width() > 0 and self.width() != self.frame_width) or (
            self.height() > 0 and self.height() != self.frame_height
        ):
            scaled = self.pixmap.scaled(
                self.width(),
                self.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.setPixmap(scaled)
        else:
            self.setPixmap(self.pixmap)

    def display_frame(self, rgb_frame, width, height):
        try:
            # Create QImage directly from numpy array (zero-copy view)
            bytes_per_line = 3 * width
            q_img = QImage(
                rgb_frame.data,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888,
            )

            self.pixmap = QPixmap.fromImage(q_img)
            self.frame_width = width
            self.frame_height = height
            self.draw()

        except Exception as e:
            logging.error(f"VideoWidget: Display error: {e}")
