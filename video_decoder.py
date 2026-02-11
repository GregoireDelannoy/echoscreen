import queue
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import logging


import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst


class VideoDecoder(QThread):
    """Hardware-accelerated H.264 decoder using GStreamer"""

    rgb_frame_signal = pyqtSignal(object, int, int)  # numpy array, width, height

    def __init__(self, width=1920, height=1080, framerate=60):
        super().__init__()
        self.width = width
        self.height = height
        self.framerate = framerate
        self.running = True
        self.byte_queue = queue.Queue(maxsize=50)  # Smaller queue for lower latency

        # Initialize GStreamer
        Gst.init(None)

        self.pipeline = None
        self.appsrc = None
        self.appsink = None

        # Frame pooling to reduce allocations
        self.frame_pool = []
        self.pool_size = 3

    def build_pipeline(self):
        try:
            # Low latency pipeline configuration
            # Key optimizations:
            # 1. Disable all buffering (max-size-buffers=1)
            # 2. Skip B-frames for lower latency
            # 3. Use hardware decoder directly if available
            # 4. Disable sync completely
            # 5. Drop old frames aggressively

            pipeline_string = (
                "appsrc name=src format=time is-live=true do-timestamp=false "
                "min-latency=0 max-latency=0 "
                "! h264parse config-interval=-1 "  # Don't wait for config
                "! queue max-size-buffers=1 max-size-time=0 max-size-bytes=0 leaky=downstream "
                # Try hardware decoder first, fallback to software
                "! vaapih264dec low-latency=true ! "  # Intel/AMD HW decoder
                "queue max-size-buffers=1 leaky=downstream ! "
                "videoconvert ! "
                "video/x-raw,format=RGB ! "
                "appsink name=sink emit-signals=true sync=false max-buffers=1 drop=true"
            )

            # Try hardware decoder first
            try:
                self.pipeline = Gst.parse_launch(pipeline_string)
                logging.info("Using VA-API hardware decoder")
            except:
                # Fallback to software decoder
                pipeline_string = pipeline_string.replace(
                    "vaapih264dec low-latency=true",
                    "avdec_h264 low-latency=true skip-frame=1",  # Skip B-frames
                )
                self.pipeline = Gst.parse_launch(pipeline_string)
                logging.warning("VA-API decoder not available, using software decoder")

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

            # Configure appsink for minimum latency
            self.appsink = self.pipeline.get_by_name("sink")
            self.appsink.set_property("emit-signals", True)
            self.appsink.set_property("sync", False)
            self.appsink.set_property("max-buffers", 1)
            self.appsink.set_property("drop", True)
            self.appsink.set_property("enable-last-sample", False)
            self.appsink.set_property("qos", False)

            # Connect to new-sample signal
            self.appsink.connect("new-sample", self.on_new_sample)

            # Bus messages
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self.on_bus_message)

            logging.info("Pipeline built successfully")
            return True

        except Exception as e:
            logging.error(f"Failed to build pipeline: {e}")
            return False

    def on_bus_message(self, bus, message):
        t = message.type

        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logging.error(f"GStreamer error: {err}, {debug}")
            self.running = False

    def on_new_sample(self, appsink):
        try:
            # Pull sample
            sample = appsink.emit("pull-sample")
            if sample is None:
                return Gst.FlowReturn.OK

            buffer = sample.get_buffer()
            caps = sample.get_caps()

            # Get dimensions
            structure = caps.get_structure(0)
            width = structure.get_value("width")
            height = structure.get_value("height")

            # Map buffer
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR

            # Use frame pool to avoid allocations
            if len(self.frame_pool) > 0:
                frame_copy = self.frame_pool.pop()
                # Reshape if needed
                if frame_copy.shape != (height, width, 3):
                    frame_copy = np.empty((height, width, 3), dtype=np.uint8)
            else:
                frame_copy = np.empty((height, width, 3), dtype=np.uint8)

            np.copyto(
                frame_copy,
                np.ndarray(
                    shape=(height, width, 3), dtype=np.uint8, buffer=map_info.data
                ),
            )

            buffer.unmap(map_info)

            self.rgb_frame_signal.emit(frame_copy, width, height)

            return Gst.FlowReturn.OK

        except Exception as e:
            logging.error(f"Sample processing error: {e}")
            return Gst.FlowReturn.ERROR

    def return_frame_to_pool(self, frame):
        if len(self.frame_pool) < self.pool_size:
            self.frame_pool.append(frame)

    def run(self):
        try:
            # Build pipeline
            if not self.build_pipeline():
                return

            # Start pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logging.error("Failed to start pipeline")
                return

            while self.running:
                try:
                    # Non-blocking get with short timeout
                    h264_data = self.byte_queue.get(timeout=0.01)
                    buf = Gst.Buffer.new_wrapped(h264_data)

                    ret = self.appsrc.emit("push-buffer", buf)
                    if ret != Gst.FlowReturn.OK and ret != Gst.FlowReturn.FLUSHING:
                        print(f"Push failed: {ret}")
                except queue.Empty:
                    continue
                except Exception as e:
                    logging.error(f"Error feeding data: {e}")

        except Exception as e:
            logging.error(f"Decoder error: {e}")
        finally:
            self.stop()

    def feed_data(self, h264_bytes):
        """Queue H.264 data - non-blocking"""
        try:
            self.byte_queue.put_nowait(h264_bytes)
        except queue.Full:
            # Drop old frame and add new one
            try:
                self.byte_queue.get_nowait()
                self.byte_queue.put_nowait(h264_bytes)
            except:
                pass

    def stop(self):
        self.running = False

        if self.appsrc:
            try:
                self.appsrc.emit("end-of-stream")
            except:
                pass

        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

        logging.info("Decoder stopped")
