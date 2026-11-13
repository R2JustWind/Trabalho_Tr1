"""Controlador da aplicação, independente de GTK."""

from __future__ import annotations

from uuid import uuid4

from .adapter import DisconnectedLinkAdapter, EventCallback, LinkAdapter
from .codec import MessageValidationError, decode_message, encode_message
from .models import (
    LinkEvent,
    RxPayload,
    SimulationConfig,
    TransmissionState,
    TxPayload,
    ValidationStatus,
)


class ChatController:
    def __init__(self, adapter: LinkAdapter | None = None, encoding: str = "utf-8"):
        self.adapter = adapter or DisconnectedLinkAdapter()
        self.encoding = encoding
        self.state = TransmissionState.IDLE
        self.last_event: LinkEvent | None = None

    def send(
        self,
        text: str,
        configuration: SimulationConfig,
        on_event: EventCallback | None = None,
    ) -> TxPayload | None:
        self._emit(LinkEvent(TransmissionState.VALIDATING), on_event)
        try:
            payload = encode_message(text, encoding=self.encoding)
        except MessageValidationError as exc:
            self._emit(LinkEvent(TransmissionState.FAILED, detail=str(exc)), on_event)
            return None

        message = TxPayload(
            payload=payload,
            encoding=self.encoding,
            message_id=uuid4().hex,
            configuration=configuration,
        )
        self._emit(
            LinkEvent(TransmissionState.SUBMITTED, message.message_id), on_event
        )
        self.adapter.submit(message, lambda event: self._emit(event, on_event))
        return message

    def receive(self, payload: RxPayload, on_event: EventCallback | None = None) -> str | None:
        if payload.validation_status is not ValidationStatus.VALID:
            self._emit(
                LinkEvent(
                    TransmissionState.REJECTED,
                    payload.message_id,
                    "Payload rejeitado pelas camadas inferiores.",
                ),
                on_event,
            )
            return None
        try:
            text = decode_message(payload.payload, encoding=payload.encoding)
        except MessageValidationError as exc:
            self._emit(LinkEvent(TransmissionState.FAILED, payload.message_id, str(exc)), on_event)
            return None
        self._emit(LinkEvent(TransmissionState.DELIVERED, payload.message_id), on_event)
        return text

    def receive_bits(
        self,
        bits,
        message_id: str,
        configuration: SimulationConfig,
        on_event: EventCallback | None = None,
    ) -> str | None:
        """Recebe bits reais do backend e delega a validacao ao adaptador."""
        receive_bits = getattr(self.adapter, "receive_bits", None)
        if receive_bits is None:
            self._emit(
                LinkEvent(
                    TransmissionState.UNAVAILABLE,
                    message_id,
                    "O adaptador atual nao fornece recepcao de bits.",
                ),
                on_event,
            )
            return None
        payload = receive_bits(
            bits,
            message_id,
            configuration,
            lambda event: self._emit(event, on_event),
        )
        return self.receive(payload, on_event)

    def _emit(self, event: LinkEvent, on_event: EventCallback | None) -> None:
        self.state = event.state
        self.last_event = event
        if on_event:
            on_event(event)
