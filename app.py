#!/usr/bin/env python3
"""
Unofficial Spacedesk client for Linux using PyQt6 and GStreamer
"""

import sys
import signal
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QTimer
import logging
import argparse

from video_decoder import VideoDecoder
from qt_video_widget import VideoWidget
from spacedesk_protocol import Streamer


class QtApplicationWindow(QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.setWindowTitle("UNOFFICIAL Linux Spacedesk client")
        self.setGeometry(100, 100, int(self.args.width / 2), int(self.args.height / 2))

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.decoder = VideoDecoder(width=args.width, height=args.height)
        self.streamer = Streamer(
            host=args.host,
            port=args.port,
            width=args.width,
            height=args.height,
            quality=args.quality,
        )

        self.display = VideoWidget()
        layout.addWidget(self.display)

        central.setLayout(layout)

        # Start immediately
        QTimer.singleShot(1, self.start_streaming)

    def on_frame_ready(self, frame, width, height):
        self.display.display_frame(frame, width, height)
        if self.decoder:
            self.decoder.return_frame_to_pool(frame)

    def on_video_data(self, data):
        if self.decoder:
            self.decoder.feed_data(data)

    def start_streaming(self):
        # Connect thread signals and start both decoder and streamer threads
        self.decoder.rgb_frame_signal.connect(
            self.on_frame_ready, Qt.ConnectionType.QueuedConnection
        )

        self.decoder.start()

        self.streamer.video_data_signal.connect(
            self.on_video_data, Qt.ConnectionType.QueuedConnection
        )

        self.streamer.start()

    def stop_streaming(self):
        if self.decoder:
            self.decoder.stop()
            self.decoder = None
        if self.streamer:
            self.streamer.stop()
            self.streamer = None

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self.display and self.display.pixmap:
            self.display.draw()

    def closeEvent(self, event):
        self.stop_streaming()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_F11, Qt.Key.Key_F):
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            # Exit full screen or close app
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
            event.accept()
        elif event.key() == Qt.Key.Key_Q:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)


def get_screen_dimensions(app):
    screen = app.primaryScreen()
    geometry = screen.geometry()
    return geometry.width(), geometry.height()


def parse_resolution(resolution_str):
    try:
        width, height = resolution_str.lower().split("x")
        width = int(width)
        height = int(height)

        if width <= 0 or height <= 0:
            raise ValueError("Width and height must be positive integers")

        return width, height
    except (ValueError, AttributeError) as e:
        raise argparse.ArgumentTypeError(
            f"Resolution must be in format WIDTHxHEIGHT (e.g., '1920x1080'): {e}"
        )


def parse_arguments(app):
    default_width, default_height = get_screen_dimensions(app)
    default_resolution = f"{default_width}x{default_height}"

    parser = argparse.ArgumentParser(
        description="Unofficial Spacedesk client for Linux using PyQt6 and GStreamer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Required: host
    parser.add_argument("host", type=str, help="Target host address")

    # Optionnal
    parser.add_argument(
        "-p", "--port", type=int, default=28252, help="Target port number"
    )

    parser.add_argument(
        "-r",
        "--resolution",
        type=str,
        default=default_resolution,
        help="Screen resolution in format WIDTHxHEIGHT (e.g., 1920x1080)",
    )

    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=100,
        choices=range(1, 101),
        metavar="[1-100]",
        help="Video quality (1-100)",
    )

    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )

    args = parser.parse_args()
    args.width, args.height = parse_resolution(args.resolution)

    return args


def setup_interrupt_handling(app, window):
    def signal_handler(sig, frame):
        logging.info("\nKeyboard interrupt received (Ctrl+C)")
        logging.info("Shutting down application...")

        window.stop_streaming()

        app.quit()

    signal.signal(signal.SIGINT, signal_handler)

    # Create a timer to allow Python to process signals
    # This is crucial - without it, Ctrl+C won't work!
    timer = QTimer()
    timer.timeout.connect(lambda: None)  # No-op to process events
    timer.start(500)  # Check every 500ms

    return timer


def main():
    app = QApplication(sys.argv)
    args = parse_arguments(app)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    window = QtApplicationWindow(args)

    # Setup keyboard interrupt handling
    # Keep timer reference to prevent garbage collection
    interrupt_timer = setup_interrupt_handling(app, window)

    window.show()
    logging.info(
        "Use F11 or F to toggle full screen, ESC to exit full screen or close app, Q to quit."
    )
    app.exec()


if __name__ == "__main__":
    main()
