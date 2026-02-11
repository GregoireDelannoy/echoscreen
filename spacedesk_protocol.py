import enum
import logging
import socket
import select
import hashlib
import uuid
from PyQt6.QtCore import QThread, pyqtSignal


def create_uuid_from_string(val: str):
    hex_string = hashlib.md5(val.encode("UTF-8")).hexdigest()
    return uuid.UUID(hex=hex_string)


class PacketType(enum.IntEnum):
    CONNECTION_START = 0
    PING = 1
    VIDEO_DATA = 2
    VIDEO_DATA_ACK = 7
    DISCONNECT = 8


def recv_until_timeout(
    sock: socket.socket, bufsize: int = 4096, timeout: float = 500
) -> bytes:
    chunks = bytearray()
    sock.settimeout(timeout)
    try:
        while True:
            data = sock.recv(bufsize)
            if not data:  # remote closed connection
                break
            chunks.extend(data)
    except socket.timeout:
        # no more data for now
        pass
    return bytes(chunks)


class Packet:
    PACKET_SIZE = 128

    def __init__(self):
        self.msg = bytearray(self.PACKET_SIZE)

    def get_bytes(self) -> bytes:
        return bytes(self.msg)


class VideoDataAckPacket(Packet):
    def __init__(self):
        super().__init__()
        self.msg[0:4] = (PacketType.VIDEO_DATA_ACK).to_bytes(4, byteorder="little")


class DisconnectPacket(Packet):
    def __init__(self):
        super().__init__()
        self.msg[0:4] = (PacketType.DISCONNECT).to_bytes(4, byteorder="little")


class ConnectionStartPacket(Packet):
    PAYLOAD_SIZE = 334

    def __init__(self, width, height, quality):
        super().__init__()
        # Build the first packet according to the observed structure in Wireshark captures of the official Windows and Android clients
        self.msg[0:4] = (PacketType.CONNECTION_START).to_bytes(4, byteorder="little")

        # Payload size. Don't know why 334 even though the payload is only identification string
        self.msg[4:8] = (self.PAYLOAD_SIZE).to_bytes(4, byteorder="little")
        self.msg[8:12] = (4).to_bytes(4, byteorder="little")
        self.msg[12:16] = (8).to_bytes(4, byteorder="little")
        self.msg[16:20] = (0).to_bytes(4, byteorder="little")
        self.msg[20:24] = (1).to_bytes(4, byteorder="little")
        self.msg[24:28] = (3).to_bytes(4, byteorder="little")
        self.msg[28:32] = (2).to_bytes(4, byteorder="little")
        # Quality settings 0 - 100
        self.msg[32:36] = (quality).to_bytes(4, byteorder="little")
        self.msg[36:38] = (4).to_bytes(2, byteorder="little")  # Compression Type = H264
        self.msg[38:40] = (1).to_bytes(2, byteorder="little")
        self.msg[40:44] = (0).to_bytes(4, byteorder="little")
        # Framerate? I have not seen any difference
        self.msg[44:46] = (60).to_bytes(2, byteorder="little")
        self.msg[46:48] = (4).to_bytes(2, byteorder="little")
        # Depends on operating system => 1 for Windows?
        self.msg[48:52] = (1).to_bytes(4, byteorder="little")

        # This seems to be used for the resolution of the virtual display
        self.msg[52:56] = (width).to_bytes(4, byteorder="little")
        # 8 * 4 bytes of empty space

        self.msg[88:92] = (height).to_bytes(4, byteorder="little")
        # 8 * 4 bytes of empty space

        # License Type. 0 = Free, 1 or 2 = Non-Commercial, 3 = Commercial. Don't know if this is actually used for anything.
        self.msg[124:128] = (0).to_bytes(4, byteorder="little")

        self.payload = bytearray(334)
        # Identification string: "{UUID based on hostname} {hostname}" keep it stable across runs
        # so the virtual screen is placed in the same position in the display arrangement on the host side
        hostname = socket.gethostname()
        identification_str = f"{{{create_uuid_from_string(hostname).hex}}} {hostname}"
        for i in range(len(identification_str)):
            self.payload[i * 2 : (i + 1) * 2] = ord(identification_str[i]).to_bytes(
                2, byteorder="little"
            )

    def get_bytes(self) -> bytes:
        msg_with_payload = bytearray(self.PACKET_SIZE + self.PAYLOAD_SIZE)
        msg_with_payload[0 : self.PACKET_SIZE] = bytes(self.msg)
        msg_with_payload[self.PACKET_SIZE : self.PACKET_SIZE + self.PAYLOAD_SIZE] = (
            bytes(self.payload)
        )

        return bytes(msg_with_payload)


def get_packet_type(data: bytes) -> PacketType | int:
    if len(data) < 4:
        raise ValueError("data too short to determine packet type")
    val = int.from_bytes(data[0:4], byteorder="little")
    try:
        return PacketType(val)
    except ValueError:
        # Unknown packet type; return the raw integer so caller can handle it
        return val


def get_payload_size(data: bytes) -> int:
    if len(data) < 8:
        raise ValueError("data too short to determine payload size")
    return int.from_bytes(data[4:8], byteorder="little")


class Streamer(QThread):
    DEFAULT_SPACEDESK_PORT = 28252
    video_data_signal = pyqtSignal(object)  # raw bytes

    def __init__(
        self, host, port=DEFAULT_SPACEDESK_PORT, width=1920, height=1080, quality=100
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.quality = quality

        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)

    def wait_for_data(self, timeout=0.1) -> bool:
        # Wait for the socket to be readable (data available) or timeout after 5 seconds
        rlist, _, _ = select.select([self.sock], [], [], timeout)
        return bool(rlist)

    def receive_size(self, size) -> bytes:
        received = bytearray()
        while len(received) < size:
            self.wait_for_data()
            chunk = self.sock.recv(size - len(received))
            if not chunk:
                raise ConnectionError("Socket closed before receiving expected data")
            received.extend(chunk)
        return bytes(received)

    def stop(self):
        self.running = False
        logging.info("Streamer stopping, sending Disconnect packet")
        disconnect_packet = DisconnectPacket()
        self.sock.sendall(disconnect_packet.get_bytes())

    def run(self):
        logging.info(
            f"Connecting to spacedesk server at {self.host}:{self.port}with resolution {self.width}x{self.height} and quality {self.quality}"
        )
        try:
            self.sock.connect((self.host, self.port))
        except Exception as e:
            logging.error(f"Error connecting to server: {e}")
            raise e

        logging.info("Connected, sending Connection Start packet")
        self.sock.sendall(
            ConnectionStartPacket(self.width, self.height, self.quality).get_bytes()
        )

        while self.running:
            if not self.wait_for_data():
                # No data received within timeout, check if we should keep running
                continue
            if not self.running:
                break

            received = self.sock.recv(Packet.PACKET_SIZE)
            if not received:
                logging.error(
                    "Error receiving packet. Should not happen in normal network conditions."
                )
                continue

            received_packet_type = get_packet_type(received)

            if received_packet_type == PacketType.PING:
                logging.info("Received Ping packet, sending Ping response")
                self.sock.sendall(received)
            elif received_packet_type == PacketType.CONNECTION_START:
                logging.info("Received CONNECTION_START packet, ignoring")
            elif received_packet_type == PacketType.VIDEO_DATA:
                payload_size = get_payload_size(received)
                logging.debug(f"Received VIDEO_DATA. Payload size: {payload_size}")
                full_payload = self.receive_size(payload_size)

                self.video_data_signal.emit(full_payload)

                # Send Framebuffer Ack packet
                ack_packet = VideoDataAckPacket()
                self.sock.sendall(ack_packet.get_bytes())
            else:
                logging.info(
                    f"Received unhandled packet type: {received_packet_type}, ignoring"
                )
