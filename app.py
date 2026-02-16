#!/usr/bin/env python3
"""
Unofficial Spacedesk client for Linux using PyQt6 and GStreamer
"""

import logging
import argparse
import queue

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk
from gi.repository import Gdk

from video_decoder import VideoDecoder
from spacedesk_protocol import Streamer


class GtkWindow:
    WINDOW_TITLE = "UNOFFICIAL Linux Spacedesk client"

    def __init__(self, width, height) -> None:
        self.isFullScreen = False
        Gtk.init(None)

        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.connect("destroy", Gtk.main_quit)

        self.window.set_name(self.WINDOW_TITLE)
        self.window.set_default_size(width, height)

        # 2. Create a drawing area where the video will render
        self.draw_area = Gtk.DrawingArea()
        self.window.add(self.draw_area)
        self.window.show_all()

    def get_draw_id(self):
        return self.draw_area.get_window().get_xid()

    def connect_events(self):
        self.window.connect("key-press-event", self.on_key_press)

    def start(self):
        self.connect_events()
        Gtk.main()

    def stop(self):
        Gtk.main_quit()

    def on_key_press(self, _, event):
        keyname = Gdk.keyval_name(event.keyval)
        print(f"Keyname: {keyname}")
        if keyname in ("F11", "f"):
            if self.isFullScreen:
                self.window.unfullscreen()
                self.isFullScreen = False
            else:
                self.window.fullscreen()
                self.isFullScreen = True
        elif keyname == "Escape":
            if self.isFullScreen:
                self.window.unfullscreen()
                self.isFullScreen = False
            else:
                self.stop()
        elif keyname == "q":
            self.stop()


class Application:
    def __init__(self, args):
        self.args = args
        self.raw_frames_queue = queue.Queue(maxsize=50)

        self.window = GtkWindow(int(self.args.width / 2), int(self.args.height / 2))
        xid = self.window.get_draw_id()
        self.decoder = VideoDecoder(
            xid, self.raw_frames_queue, self.args.width, self.args.height
        )
        self.streamer = Streamer(
            self.decoder.push_data,
            self.args.host,
            self.args.port,
            self.args.width,
            self.args.height,
            self.args.quality,
        )

    def start(self):
        try:
            self.decoder.start()
            self.streamer.start()
            self.window.start()
        except KeyboardInterrupt:
            logging.info("Keyboard interrrupt, closing connections")
        except Exception as e:
            logging.error(f"Runtime error: {e}")
        finally:
            self.stop()

    def stop(self):
        if self.decoder:
            self.decoder.stop()
            self.decoder = None
        if self.streamer:
            self.streamer.stop()
            self.streamer = None
        self.window.stop()


def get_screen_dimensions():
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor()
    scale_factor = monitor.get_scale_factor()
    geometry = monitor.get_geometry()
    return geometry.width * scale_factor, geometry.height * scale_factor


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


def parse_arguments():
    default_width, default_height = get_screen_dimensions()
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

    # parser.add_argument(
    #     "-f",
    #     "--framerate",
    #     type=int,
    #     default=60,
    #     choices=[30,60,120],
    #     metavar="[30,60,120]",
    #     help="Framerate, frames per second",
    # )

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


def main():
    args = parse_arguments()
    app = Application(args)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    logging.info(
        "Use F11 or F to toggle full screen, ESC to exit full screen or close app, Q to quit."
    )

    app.start()


if __name__ == "__main__":
    main()
