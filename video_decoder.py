import logging


import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gst
from gi.repository import (
    GstVideo,
)  # Seems useless, but if not present xvimagesink opens in another window


class VideoDecoder:
    def __init__(
        self, x_window_id, raw_frames_queue, width=1920, height=1080, framerate=60
    ):
        self.x_window_id = x_window_id
        self.raw_frames_queue = raw_frames_queue
        self.width = width
        self.height = height
        self.framerate = framerate

        Gst.init(None)

        self.pipeline = None
        self.appsrc = None

    def build_pipeline(self):
        try:
            pipeline_string = (
                "appsrc name=src format=time is-live=true do-timestamp=false "
                "min-latency=0 max-latency=0 "
                "! queue max-size-buffers=1 max-size-time=0 max-size-bytes=0 leaky=downstream "
                "! h264parse config-interval=-1 "
                "! vah264dec "
                "! xvimagesink name=sink sync=false qos=false"
            )

            self.pipeline = Gst.parse_launch(pipeline_string)
            self.pipeline.set_property("latency", 0)

            # Configure appsrc for minimum latency
            self.appsrc = self.pipeline.get_by_name("src")
            self.appsrc.set_property("format", Gst.Format.TIME)
            self.appsrc.set_property("stream-type", 0)  # GST_APP_STREAM_TYPE_STREAM
            self.appsrc.set_property("is-live", True)
            self.appsrc.set_property("do-timestamp", False)
            self.appsrc.set_property("min-latency", 0)
            self.appsrc.set_property("max-latency", 0)
            self.appsrc.set_property("block", False)
            self.appsrc.set_property("max-bytes", 1024 * 1024)  # Small buffer

            # Set caps
            caps = Gst.Caps.from_string(
                f"video/x-h264,stream-format=byte-stream,alignment=au,"
                f"width={self.width},height={self.height},framerate={self.framerate}/1,"
                f"profile=baseline"  # Baseline profile for lower latency
            )
            self.appsrc.set_property("caps", caps)

            # Bus messages
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.enable_sync_message_emission()
            bus.connect("sync-message::element", self.on_sync_message)
            bus.connect("message", self.on_bus_message)

            logging.info("Pipeline built successfully")
        except Exception as e:
            logging.error(f"Failed to build pipeline: {e}")
            raise e

    def on_sync_message(self, _, msg):
        if msg.get_structure().get_name() == "prepare-window-handle":
            # Tell GStreamer to draw inside our widget
            msg.src.set_window_handle(self.x_window_id)

    def on_bus_message(self, _, message):
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logging.error(f"GStreamer error: {err}, {debug}")
            self.running = False

    def push_data(self, h264_data):
        buf = Gst.Buffer.new_wrapped(h264_data)
        buf.set_flags(Gst.BufferFlags.DISCONT)  # If you detect gaps
        ret = self.appsrc.emit("push-buffer", buf)
        if ret != Gst.FlowReturn.OK and ret != Gst.FlowReturn.FLUSHING:
            logging.error(f"Push failed: {ret}")

    def start(self):
        self.build_pipeline()
        self.pipeline.set_state(Gst.State.PLAYING)

    def stop(self):
        if self.appsrc:
            try:
                self.appsrc.emit("end-of-stream")
            except:
                pass

        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

        logging.info("Decoder stopped")
