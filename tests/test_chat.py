import threading
import unittest

from InterfaceGUI import LinkAdapter
from InterfaceGUI import MessageValidationError, decode_message, encode_message
from InterfaceGUI import ChatController, SimulatorAdapter
from InterfaceGUI import (
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

    def test_simulator_adapter_runs_end_to_end(self):
        events = []
        finished = threading.Event()
        controller = ChatController(SimulatorAdapter())

        def on_event(event):
            events.append(event)
            if event.state in {
                TransmissionState.DELIVERED,
                TransmissionState.REJECTED,
                TransmissionState.FAILED,
            }:
                finished.set()

        controller.send("A" * 300, SimulationConfig(), on_event)
        self.assertTrue(finished.wait(10), "o simulador nao concluiu em 10 segundos")
        self.assertEqual(events[-1].state, TransmissionState.DELIVERED)
        self.assertIn("bits_aplicacao", events[-1].telemetry)
        self.assertIn("sinal_tx_volts", events[-1].telemetry)


if __name__ == "__main__":
    unittest.main()
