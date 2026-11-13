"""Adaptadores entre a aplicacao e a API publica da camada de enlace."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable

from enlace.CamadaEnlace import (
    ConfiguracaoEnlace,
    TipoControleErro,
    TipoEnquadramento,
    bits_para_bytes,
    bytes_para_bits,
    camada_enlace_receptora,
    camada_enlace_transmissora,
)

from .models import LinkEvent, RxPayload, TransmissionState, TxPayload, ValidationStatus

EventCallback = Callable[[LinkEvent], None]


class LinkAdapter(ABC):
    @abstractmethod
    def submit(self, payload: TxPayload, on_event: EventCallback) -> None:
        """Entrega o payload para a camada de enlace."""

    def receive_bits(self, bits: Iterable[int | str], message_id: str, configuration, on_event: EventCallback) -> RxPayload:
        """Converte bits recebidos externamente em payload validado."""
        raise NotImplementedError


class DisconnectedLinkAdapter(LinkAdapter):
    """Stub explicito enquanto as camadas de integracao nao estao conectadas."""

    def submit(self, payload: TxPayload, on_event: EventCallback) -> None:
        on_event(LinkEvent(TransmissionState.UNAVAILABLE, payload.message_id,
                           "Camada de enlace aguardando integracao; nenhuma entrega foi feita."))

    def receive(self, payload: RxPayload, on_event: EventCallback) -> None:
        state = (TransmissionState.DELIVERED
                 if payload.metadata.get("backend_event", False)
                 and payload.validation_status is ValidationStatus.VALID
                 else TransmissionState.REJECTED)
        on_event(LinkEvent(state, payload.message_id, "Evento recebido do backend de teste."))

    def receive_bits(self, bits, message_id: str, configuration, on_event: EventCallback) -> RxPayload:
        on_event(LinkEvent(
            TransmissionState.UNAVAILABLE,
            message_id,
            "Recepcao de bits indisponivel no adaptador desconectado.",
        ))
        return RxPayload(b"", "utf-8", message_id, ValidationStatus.REJECTED)


class EnlaceLinkAdapter(LinkAdapter):
    """Traduz o contrato da aplicacao para a API existente em ``enlace``.

    Nao executa fisica, canal ou ruido. No TX entrega bits enquadrados por
    evento PROCESSING; no RX consome bits externos e retorna payload validado.
    """

    _FRAMING = {
        "contagem de caracteres": TipoEnquadramento.CONTAGEM_CARACTERES,
        "entrelacamento de bits": TipoEnquadramento.ENTRELACAMENTO_BITS,
        "entrelaçamento de bits": TipoEnquadramento.ENTRELACAMENTO_BITS,
        "byte stuffing": TipoEnquadramento.BYTE_STUFFING,
        "bit stuffing": TipoEnquadramento.BIT_STUFFING,
    }
    _ERROR = {
        "nenhum": TipoControleErro.NENHUM,
        "paridade par": TipoControleErro.PARIDADE_PAR,
        "checksum": TipoControleErro.CHECKSUM,
        "crc-32": TipoControleErro.CRC32,
        "hamming": TipoControleErro.HAMMING,
    }

    def submit(self, payload: TxPayload, on_event: EventCallback) -> None:
        config = self._config(payload.configuration)
        tx_bits = camada_enlace_transmissora(bytes_para_bits(payload.payload), config)
        on_event(LinkEvent(
            TransmissionState.PROCESSING,
            payload.message_id,
            "Payload processado pelo enlace; aguardando fisica/canal.",
            {"enlace_tx_bits": tx_bits},
        ))

    def receive_bits(self, bits: Iterable[int | str], message_id: str, configuration, on_event: EventCallback) -> RxPayload:
        resultado = camada_enlace_receptora(bits, self._config(configuration))
        rejeitado = resultado.houve_descarte
        payload = bytes(bits_para_bytes(resultado.payload)) if not rejeitado else b""
        statuses = [{"index": item.indice, "status": item.situacao.value, "detail": item.detalhe}
                    for item in resultado.quadros]
        rx = RxPayload(payload, "utf-8", message_id,
                       ValidationStatus.REJECTED if rejeitado else ValidationStatus.VALID,
                       {"enlace_quadros": statuses})
        on_event(LinkEvent(
            TransmissionState.REJECTED if rejeitado else TransmissionState.DELIVERED,
            message_id,
            "Quadro rejeitado pelo enlace." if rejeitado else "Quadro validado pelo enlace.",
            {"enlace_rx_quadros": statuses},
        ))
        return rx

    @classmethod
    def _config(cls, configuration) -> ConfiguracaoEnlace:
        try:
            framing = cls._FRAMING[configuration.framing_method.casefold()]
            error = cls._ERROR[configuration.error_control_method.casefold()]
        except KeyError as exc:
            raise ValueError(f"Opcao de enlace nao suportada: {exc.args[0]}") from exc
        return ConfiguracaoEnlace(
            enquadramento=framing,
            controle_erro=error,
            tamanho_max_quadro=configuration.frame_size,
            tamanho_checksum=configuration.edc_size or 16,
        )
