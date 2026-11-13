"""Tipos do contrato da aplicação com as camadas inferiores.

Os nomes e campos são uma implementação local do contrato provisório. Eles não
representam APIs já validadas pelos responsáveis pelas outras camadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class TransmissionState(str, Enum):
    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class ValidationStatus(str, Enum):
    VALID = "valid"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SimulationConfig:
    """Configuração encaminhada ao backend, sem executar seus algoritmos."""

    frame_size: int = 1024
    edc_size: int = 0
    framing_method: str = "contagem de caracteres"
    error_control_method: str = "paridade par"
    baseband_modulation: str = "NRZ-Polar"
    carrier_modulation: str = "ASK"
    noise_mean: float = 0.0
    noise_standard_deviation: float = 0.0


@dataclass(frozen=True)
class TxPayload:
    payload: bytes
    encoding: str
    message_id: str
    configuration: SimulationConfig


@dataclass(frozen=True)
class RxPayload:
    payload: bytes
    encoding: str
    message_id: str
    validation_status: ValidationStatus
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LinkEvent:
    state: TransmissionState
    message_id: str | None = None
    detail: str = ""
    telemetry: Mapping[str, Any] = field(default_factory=dict)
