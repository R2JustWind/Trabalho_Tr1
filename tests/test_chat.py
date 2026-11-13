import unittest

from interface.adapter import LinkAdapter
from interface.codec import MessageValidationError, decode_message, encode_message
from interface.controller import ChatController
from interface.models import (
    LinkEvent,
    RxPayload,
    SimulationConfig,
    TransmissionState,
    TxPayload,
    ValidationStatus,
)


class RecordingAdapter(LinkAdapter):
    def __init__(self):
        self.payloads = []

    def submit(self, payload: TxPayload, on_event):
        self.payloads.append(payload)
        on_event(LinkEvent(TransmissionState.PROCESSING, payload.message_id, "mock"))


class ChatTests(unittest.TestCase):
    def test_utf8_round_trip(self):
        text = "Olá, TR1 🌐"
        self.assertEqual(decode_message(encode_message(text)), text)

    def test_empty_message_is_rejected(self):
        with self.assertRaises(MessageValidationError):
            encode_message("   ")

    def test_send_passes_utf8_bytes_to_adapter(self):
        adapter = RecordingAdapter()
        controller = ChatController(adapter)
        message = controller.send("ação", SimulationConfig())
        self.assertEqual(adapter.payloads[0], message)
        self.assertEqual(message.payload, "ação".encode("utf-8"))
        self.assertEqual(controller.state, TransmissionState.PROCESSING)

    def test_disconnected_adapter_never_reports_delivery(self):
        controller = ChatController()
        events = []
        controller.send("teste", SimulationConfig(), events.append)
        self.assertEqual(events[-1].state, TransmissionState.UNAVAILABLE)
        self.assertNotEqual(controller.state, TransmissionState.DELIVERED)

    def test_only_validated_rx_payload_is_displayable(self):
        controller = ChatController()
        rejected = RxPayload(b"oculta", "utf-8", "1", ValidationStatus.REJECTED)
        self.assertIsNone(controller.receive(rejected))
        valid = RxPayload(b"recebida", "utf-8", "2", ValidationStatus.VALID)
        self.assertEqual(controller.receive(valid), "recebida")


if __name__ == "__main__":
    unittest.main()
