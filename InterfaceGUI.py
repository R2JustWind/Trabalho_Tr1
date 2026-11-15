"""Interface GTK e aplicacao de chat do simulador TR1.

Este arquivo concentra a camada de aplicacao/interface. As camadas de enlace,
fisica, canal e simulador permanecem em seus respectivos pacotes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import threading
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from enlace.CamadaEnlace import (
    ConfiguracaoEnlace,
    TipoControleErro,
    TipoEnquadramento,
    bits_para_bytes,
    bytes_para_bits,
    camada_enlace_receptora,
    camada_enlace_transmissora,
)


# FLUXO DA APLICACAO
#
# TX: texto digitado -> bytes (UTF-8) -> bits -> camada de enlace -> fisica/canal.
# RX: fisica/canal -> bits -> enlace validado -> bytes -> texto exibido.
#
# Este arquivo faz a fronteira entre o usuario e as camadas do simulador. Ele
# nao implementa enquadramento, modulacao, canal ou ruido; apenas transforma
# dados, encaminha chamadas e apresenta estados/telemetria recebidos.


# ---------------------------------------------------------------------------
# Modelos do contrato da aplicacao

class TransmissionState(str, Enum):
    """Estados observaveis de uma mensagem durante TX/RX."""

    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class ValidationStatus(str, Enum):
    """Resultado da validacao feita pelas camadas inferiores."""

    VALID = "valid"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SimulationConfig:
    """Parametros escolhidos na GUI e encaminhados ao simulador.

    As opcoes de fisica, canal e enlace sao somente valores de configuracao
    nesta camada; seus algoritmos pertencem aos respectivos pacotes.
    """

    # 32 bytes segue o padrao seguro do enlace e deixa margem para EDC/cabecalho.
    frame_size: int = 32
    edc_size: int = 0
    framing_method: str = "contagem de caracteres"
    error_control_method: str = "paridade par"
    baseband_modulation: str = "NRZ-Polar"
    carrier_modulation: str = "ASK"
    noise_mean: float = 0.0
    noise_standard_deviation: float = 0.0


@dataclass(frozen=True)
class TxPayload:
    """Mensagem convertida em bytes pronta para atravessar a pilha TX."""

    payload: bytes
    encoding: str
    message_id: str
    configuration: SimulationConfig


@dataclass(frozen=True)
class RxPayload:
    """Mensagem recebida somente depois de uma validacao declarada pelo backend."""

    payload: bytes
    encoding: str
    message_id: str
    validation_status: ValidationStatus
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LinkEvent:
    """Atualizacao de estado e telemetria enviada para a GUI."""

    state: TransmissionState
    message_id: str | None = None
    detail: str = ""
    telemetry: Mapping[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Conversao texto <-> bytes

DEFAULT_ENCODING = "utf-8"


class MessageValidationError(ValueError):
    """Entrada que nao pode ser enviada ou decodificada como texto."""


def encode_message(text: str, *, encoding: str = DEFAULT_ENCODING) -> bytes:
    """Valida o texto do usuario e o converte para bytes.

    O encoding fica explicito no payload para que o receptor use a mesma
    convencao. Mensagens vazias e erros de conversao nao chegam ao enlace.
    """

    if not isinstance(text, str):
        raise MessageValidationError("A mensagem precisa ser texto.")
    if not text.strip():
        raise MessageValidationError("Digite uma mensagem antes de enviar.")
    try:
        return text.encode(encoding)
    except UnicodeEncodeError as exc:
        raise MessageValidationError(
            f"A mensagem nao pode ser convertida com {encoding}."
        ) from exc


def decode_message(payload: bytes, *, encoding: str = DEFAULT_ENCODING) -> str:
    """Converte bytes validados pelo backend de volta para texto legivel."""

    if not isinstance(payload, bytes):
        raise MessageValidationError("O payload recebido precisa ser bytes.")
    try:
        return payload.decode(encoding)
    except UnicodeDecodeError as exc:
        raise MessageValidationError(
            f"O payload nao e texto valido em {encoding}."
        ) from exc


# ---------------------------------------------------------------------------
# Adaptadores de enlace

EventCallback = Callable[[LinkEvent], None]


class LinkAdapter(ABC):
    """Porta minima entre a aplicacao e uma implementacao de backend."""

    @abstractmethod
    def submit(self, payload: TxPayload, on_event: EventCallback) -> None:
        """Entrega o payload para a camada de enlace."""

    def receive_bits(
        self,
        bits: Iterable[int | str],
        message_id: str,
        configuration: SimulationConfig,
        on_event: EventCallback,
    ) -> RxPayload:
        """Recebe bits externos; subclasses definem a validacao apropriada."""

        raise NotImplementedError


class DisconnectedLinkAdapter(LinkAdapter):
    """Stub para testes quando o backend ainda nao esta conectado."""

    def submit(self, payload: TxPayload, on_event: EventCallback) -> None:
        """Informa indisponibilidade sem simular entrega."""

        on_event(LinkEvent(
            TransmissionState.UNAVAILABLE,
            payload.message_id,
            "Camada de enlace aguardando integracao; nenhuma entrega foi feita.",
        ))

    def receive_bits(self, bits, message_id: str, configuration, on_event: EventCallback) -> RxPayload:
        """Mantem o comportamento seguro quando nao existe backend conectado."""

        on_event(LinkEvent(
            TransmissionState.UNAVAILABLE,
            message_id,
            "Recepcao de bits indisponivel no adaptador desconectado.",
        ))
        return RxPayload(b"", DEFAULT_ENCODING, message_id, ValidationStatus.REJECTED)


class EnlaceLinkAdapter(LinkAdapter):
    """Traduz o contrato da aplicacao para a API publica do enlace.

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
        """Converte o payload e chama somente a transmissao publica do enlace.

        O estado permanece PROCESSING porque os bits ainda precisam atravessar
        a camada fisica e o canal antes de poderem ser considerados entregues.
        """

        config = self._config(payload.configuration)
        tx_bits = camada_enlace_transmissora(bytes_para_bits(payload.payload), config)
        on_event(LinkEvent(
            TransmissionState.PROCESSING,
            payload.message_id,
            "Payload processado pelo enlace; aguardando fisica/canal.",
            {"enlace_tx_bits": tx_bits},
        ))

    def receive_bits(
        self,
        bits: Iterable[int | str],
        message_id: str,
        configuration: SimulationConfig,
        on_event: EventCallback,
    ) -> RxPayload:
        """Valida bits recebidos pelo enlace e produz um payload de aplicacao."""

        resultado = camada_enlace_receptora(bits, self._config(configuration))
        rejected = resultado.houve_descarte
        payload = bytes(bits_para_bytes(resultado.payload)) if not rejected else b""
        statuses = [
            {"index": item.indice, "status": item.situacao.value, "detail": item.detalhe}
            for item in resultado.quadros
        ]
        rx = RxPayload(
            payload,
            DEFAULT_ENCODING,
            message_id,
            ValidationStatus.REJECTED if rejected else ValidationStatus.VALID,
            {"enlace_quadros": statuses},
        )
        on_event(LinkEvent(
            TransmissionState.REJECTED if rejected else TransmissionState.DELIVERED,
            message_id,
            "Quadro rejeitado pelo enlace." if rejected else "Quadro validado pelo enlace.",
            {"enlace_rx_quadros": statuses},
        ))
        return rx

    @classmethod
    def _config(cls, configuration: SimulationConfig) -> ConfiguracaoEnlace:
        """Traduz nomes exibidos na GUI para enums da API do enlace."""

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


class SimulatorAdapter(LinkAdapter):
    """Adaptador ponta a ponta entre a GUI e a API publica do simulador.

    O simulador executa TX/RX em suas proprias threads, mas ``enviar`` bloqueia
    o chamador ate retornar. Por isso este adaptador cria uma thread de trabalho
    adicional e envia um unico resultado final para a GUI.
    """

    _BASEBAND = {
        "nrz-polar": "nrz_polar",
        "manchester": "manchester",
        "bipolar": "bipolar",
    }
    _CARRIER = {
        "ask": "ask",
        "fsk": "fsk",
        "8psk": "8psk",
        "32-qam": "qam32",
    }

    def submit(self, payload: TxPayload, on_event: EventCallback) -> None:
        on_event(LinkEvent(
            TransmissionState.PROCESSING,
            payload.message_id,
            "Simulacao TX/RX em andamento.",
        ))
        worker = threading.Thread(
            target=self._run,
            args=(payload, on_event),
            name="InterfaceGUI-Simulador",
            daemon=True,
        )
        worker.start()

    @classmethod
    def _physics_config(cls, configuration: SimulationConfig) -> dict[str, Any]:
        """Traduz as opcoes visuais para o dicionario da camada fisica."""
        try:
            baseband = cls._BASEBAND[configuration.baseband_modulation.casefold()]
            carrier = cls._CARRIER[configuration.carrier_modulation.casefold()]
        except KeyError as exc:
            raise ValueError(f"Opcao de fisica nao suportada: {exc.args[0]}") from exc
        return {
            "banda_base": baseband,
            "modulacao": carrier,
            "taxa_amostragem": 40_000,
            "frequencia_portadora": 1_000,
            "amplitude": 1.0,
        }

    @classmethod
    def _simulation_config(cls, configuration: SimulationConfig):
        """Monta a configuracao do simulador sem duplicar seus algoritmos."""
        from simulador.Simulador import ConfiguracaoSimulacao

        return ConfiguracaoSimulacao(
            enlace=EnlaceLinkAdapter._config(configuration),
            media_ruido=configuration.noise_mean,
            desvio_ruido=configuration.noise_standard_deviation,
            codificacao=DEFAULT_ENCODING,
        )

    @classmethod
    def _run_physical_tx(cls, bits, physics_config):
        from fisica.CamadaFisica import fisica_tx

        return fisica_tx(bits, physics_config)["sinal"]

    @classmethod
    def _run_physical_rx(cls, signal, physics_config):
        from fisica.CamadaFisica import fisica_rx

        return fisica_rx(signal, physics_config)["bits"]

    def _run(self, payload: TxPayload, on_event: EventCallback) -> None:
        try:
            from simulador.Simulador import Simulador

            simulation_config = self._simulation_config(payload.configuration)
            physics_config = self._physics_config(payload.configuration)
            simulator = Simulador(
                simulation_config,
                fisica_transmissora=lambda bits: self._run_physical_tx(bits, physics_config),
                fisica_receptora=lambda signal: self._run_physical_rx(signal, physics_config),
            )
            result = simulator.enviar(decode_message(payload.payload, encoding=payload.encoding))
            rejected = result.recepcao_enlace.houve_descarte
            statuses = [
                {"index": item.indice, "status": item.situacao.value, "detail": item.detalhe}
                for item in result.recepcao_enlace.quadros
            ]
            rx_payload = RxPayload(
                payload=(
                    bytes(bits_para_bytes(result.recepcao_enlace.payload))
                    if not rejected else b""
                ),
                encoding=payload.encoding,
                message_id=payload.message_id,
                validation_status=(
                    ValidationStatus.REJECTED if rejected else ValidationStatus.VALID
                ),
                metadata={"quadros": statuses},
            )
            telemetry = {
                "bits_aplicacao": result.bits_aplicacao,
                "bits_enlace_tx": result.bits_enlace_tx,
                "bits_fisica_rx": result.bits_fisica_rx,
                "sinal_tx_volts": result.sinal_tx,
                "sinal_rx_volts": result.sinal_rx,
                "quadros_enlace": statuses,
                "__rx_payload": rx_payload,
            }
            on_event(LinkEvent(
                TransmissionState.REJECTED if rejected else TransmissionState.DELIVERED,
                payload.message_id,
                "Quadro(s) descartado(s) pelo enlace." if rejected else "Mensagem entregue ao RX.",
                telemetry,
            ))

        except Exception as exc:
            on_event(LinkEvent(
                TransmissionState.FAILED,
                payload.message_id,
                f"Falha na simulacao: {exc}",
            ))


MAX_PLOT_POINTS = 5_000
TELEMETRY_PREVIEW_ITEMS = 8


# ---------------------------------------------------------------------------
# Controlador da aplicacao

class ChatController:
    """Coordena validacao, conversao e eventos sem depender de widgets GTK."""

    def __init__(self, adapter: LinkAdapter | None = None, encoding: str = DEFAULT_ENCODING):
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
        """Executa o fluxo TX ate o adaptador e publica cada estado."""

        self._emit(LinkEvent(TransmissionState.VALIDATING), on_event)
        try:
            payload = encode_message(text, encoding=self.encoding)
        except MessageValidationError as exc:
            self._emit(LinkEvent(TransmissionState.FAILED, detail=str(exc)), on_event)
            return None
        message = TxPayload(payload, self.encoding, uuid4().hex, configuration)
        self._emit(LinkEvent(TransmissionState.SUBMITTED, message.message_id), on_event)
        self.adapter.submit(message, lambda event: self._emit(event, on_event))
        return message

    def receive(self, payload: RxPayload, on_event: EventCallback | None = None) -> str | None:
        """Exibe somente payload validado e decodificavel."""

        if payload.validation_status is not ValidationStatus.VALID:
            self._emit(LinkEvent(
                TransmissionState.REJECTED,
                payload.message_id,
                "Payload rejeitado pelas camadas inferiores.",
            ), on_event)
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
        """Recebe bits do backend e delega sua validacao ao adaptador."""

        receive_bits = getattr(self.adapter, "receive_bits", None)
        if receive_bits is None:
            self._emit(LinkEvent(
                TransmissionState.UNAVAILABLE,
                message_id,
                "O adaptador atual nao fornece recepcao de bits.",
            ), on_event)
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


# ---------------------------------------------------------------------------
# GUI GTK3

# Estes valores alimentam os controles da Figura 1 do enunciado. Selecionar
# uma opcao nao executa o protocolo: apenas prepara SimulationConfig.

METHODS = {
    "framing": ["contagem de caracteres", "entrelaçamento de bits", "byte stuffing", "bit stuffing"],
    "error": ["paridade par", "checksum", "CRC-32", "Hamming"],
    "baseband": ["NRZ-Polar", "Manchester", "Bipolar"],
    "carrier": ["ASK", "FSK", "8PSK", "32-QAM"],
}

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk
except (ImportError, ValueError):  # pragma: no cover - depende do Linux/GTK
    Gtk = None
    GLib = None

try:
    from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
    from matplotlib.figure import Figure
except ImportError:  # pragma: no cover - dependencia opcional do ambiente
    Figure = None
    FigureCanvas = None


def require_gtk() -> None:
    """Falha com mensagem clara quando a aplicacao e iniciada sem GTK3."""

    if Gtk is None:
        raise RuntimeError("GTK3/PyGObject nao esta instalado neste ambiente Linux.")


if Gtk is not None:  # pragma: no cover - requer display GTK

    class ChatWindow(Gtk.Window):
        """Janela principal com paineis TX, RX, configuracao e telemetria."""

        def __init__(self, controller: ChatController | None = None):
            super().__init__(title="TR1 - Chat de Teleinformatica")
            self.set_default_size(900, 650)
            self.controller = controller or ChatController(SimulatorAdapter())
            self.send_button = None
            self._build()

        def _build(self) -> None:
            """Monta a composicao visual sem acoplar widgets aos algoritmos."""

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            root.set_border_width(12)
            self.add(root)
            title = Gtk.Label(label="Aplicacao de rede - Chat TX/RX")
            title.set_xalign(0)
            root.pack_start(title, False, False, 0)
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            root.pack_start(content, True, True, 0)
            content.pack_start(self._build_tx(), True, True, 0)
            content.pack_start(self._build_rx(), True, True, 0)
            root.pack_start(self._build_config(), False, False, 0)
            root.pack_start(self._build_telemetry(), True, True, 0)

        def _frame(self, title: str):
            """Cria um agrupador visual reutilizavel para cada painel."""

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_border_width(8)
            frame = Gtk.Frame(label=title)
            frame.add(box)
            return frame, box

        def _build_tx(self):
            """Cria a entrada de texto e a acao de envio do transmissor."""

            frame, box = self._frame("TX - Transmissor")
            self.input = Gtk.Entry()
            self.input.set_placeholder_text("Digite a mensagem")
            box.pack_start(self.input, False, False, 0)
            send = Gtk.Button(label="Enviar")
            send.connect("clicked", self._send)
            self.send_button = send
            box.pack_start(send, False, False, 0)
            return frame

        def _build_rx(self):
            """Cria a area que recebe texto validado do receptor."""

            frame, box = self._frame("RX - Receptor")
            self.received = Gtk.Label(label="Nenhuma mensagem recebida.")
            self.received.set_xalign(0)
            self.received.set_line_wrap(True)
            box.pack_start(self.received, True, True, 0)
            return frame

        def _combo(self, values: list[str], default: str):
            """Cria uma selecao GTK a partir das opcoes do enunciado."""

            combo = Gtk.ComboBoxText()
            for value in values:
                combo.append_text(value)
            combo.set_active(values.index(default))
            return combo

        def _build_config(self):
            """Cria controles de enlace, fisica e ruido para a configuracao."""

            frame, grid_box = self._frame("Configuracao geral")
            grid = Gtk.Grid(column_spacing=8, row_spacing=5)
            grid_box.pack_start(grid, False, False, 0)
            self.controls = {}
            fields = [
                ("Enquadramento", "framing", METHODS["framing"]),
                ("Deteccao/correcao", "error", METHODS["error"]),
                ("Modulacao banda-base", "baseband", METHODS["baseband"]),
                ("Modulacao portadora", "carrier", METHODS["carrier"]),
            ]
            for row, (label, key, values) in enumerate(fields):
                grid.attach(Gtk.Label(label=label), 0, row, 1, 1)
                combo = self._combo(values, values[0])
                self.controls[key] = combo
                grid.attach(combo, 1, row, 1, 1)
            numeric = [
                ("Tamanho maximo do quadro", "frame_size", "32"),
                ("Tamanho do EDC", "edc_size", "0"),
                ("Media AWGN (V/W)", "noise_mean", "0"),
                ("Desvio AWGN (V/W)", "noise_std", "0"),
            ]
            for row, (label, key, default) in enumerate(numeric, start=4):
                grid.attach(Gtk.Label(label=label), 0, row, 1, 1)
                entry = Gtk.Entry()
                entry.set_text(default)
                self.controls[key] = entry
                grid.attach(entry, 1, row, 1, 1)
            return frame

        def _build_telemetry(self):
            """Cria a area que apresenta estados e telemetria real."""

            frame, box = self._frame("Status e telemetria")
            self.status = Gtk.Label(label="UNAVAILABLE - aguardando integracao")
            self.status.set_xalign(0)
            box.pack_start(self.status, False, False, 0)
            self.telemetry = Gtk.TextView()
            self.telemetry.set_editable(False)
            self.telemetry.get_buffer().set_text("Bits e amostras indisponiveis ate o backend fornecer dados.")
            box.pack_start(self.telemetry, True, True, 0)
            self._build_plots(box)
            return frame

        def _build_plots(self, box) -> None:
            """Cria os graficos TX/RX quando Matplotlib GTK estiver disponivel."""
            if Figure is None or FigureCanvas is None:
                box.pack_start(
                    Gtk.Label(label="Graficos indisponiveis: instale python3-matplotlib."),
                    False,
                    False,
                    0,
                )
                self.figure = None
                self.canvas = None
                return
            self.figure = Figure(figsize=(8, 4), dpi=90)
            self.plot_tx = self.figure.add_subplot(211)
            self.plot_rx = self.figure.add_subplot(212)
            self.plot_tx.set_title("Sinal TX (V/W)")
            self.plot_rx.set_title("Sinal RX (V/W)")
            self.canvas = FigureCanvas(self.figure)
            box.pack_start(self.canvas, True, True, 0)

        def _config(self) -> SimulationConfig:
            """Le e valida os campos da GUI antes de criar a configuracao."""

            def integer(key: str) -> int:
                value = int(self.controls[key].get_text())
                if value < 0:
                    raise ValueError("valores inteiros nao podem ser negativos")
                return value

            config = SimulationConfig(
                frame_size=integer("frame_size"),
                edc_size=integer("edc_size"),
                framing_method=self.controls["framing"].get_active_text(),
                error_control_method=self.controls["error"].get_active_text(),
                baseband_modulation=self.controls["baseband"].get_active_text(),
                carrier_modulation=self.controls["carrier"].get_active_text(),
                noise_mean=float(self.controls["noise_mean"].get_text()),
                noise_standard_deviation=float(self.controls["noise_std"].get_text()),
            )
            if config.frame_size == 0:
                raise ValueError("o tamanho maximo do quadro deve ser maior que zero")
            if config.frame_size > 255:
                raise ValueError("o tamanho maximo do quadro deve ser no maximo 255 bytes")
            if config.noise_standard_deviation < 0:
                raise ValueError("o desvio padrao nao pode ser negativo")
            if config.error_control_method == "checksum" and config.edc_size not in (8, 16, 32):
                raise ValueError("o tamanho do EDC do checksum deve ser 8, 16 ou 32")
            return config

        def _send(self, _button) -> None:
            """Valida a configuracao e inicia o fluxo TX do controlador."""

            try:
                configuration = self._config()
            except ValueError as exc:
                self.status.set_text(f"FAILED - configuracao invalida: {exc}")
                return
            if self.send_button is not None:
                self.send_button.set_sensitive(False)
            self.controller.send(self.input.get_text(), configuration, self._event)

        def present_received(self, payload: RxPayload) -> None:
            """Apresenta a mensagem apenas apos a validacao do controlador."""

            text = self.controller.receive(payload, self._event)
            if text is not None:
                self.received.set_text(text)

        def _event(self, event: LinkEvent) -> None:
            """Atualiza status e telemetria sem inventar dados intermediarios."""
            if GLib is not None:
                GLib.idle_add(self._apply_event, event)
            else:
                self._apply_event(event)

        def _apply_event(self, event: LinkEvent) -> bool:
            """Atualiza widgets na thread GTK, inclusive resultado do simulador."""
            self.status.set_text(f"{event.state.value} - {event.detail or 'sem detalhe'}")
            if event.telemetry:
                visible = {
                    name: value
                    for name, value in event.telemetry.items()
                    if name != "__rx_payload"
                }
                self.telemetry.get_buffer().set_text(
                    "\n".join(
                        f"{name}: {self._format_telemetry(name, value)}"
                        for name, value in visible.items()
                    )
                )
                received = event.telemetry.get("__rx_payload")
                if isinstance(received, RxPayload):
                    text = self.controller.receive(received)
                    if text is not None:
                        self.received.set_text(text)
                self._plot_signals(
                    event.telemetry.get("sinal_tx_volts", []),
                    event.telemetry.get("sinal_rx_volts", []),
                )
            if event.state in {
                TransmissionState.DELIVERED,
                TransmissionState.REJECTED,
                TransmissionState.FAILED,
                TransmissionState.UNAVAILABLE,
            } and self.send_button is not None:
                self.send_button.set_sensitive(True)
            return False

        @staticmethod
        def _format_telemetry(name: str, value: Any) -> str:
            """Resume vetores grandes para evitar sobrecarregar o GTK."""
            vector_names = {
                "bits_aplicacao",
                "bits_enlace_tx",
                "bits_fisica_rx",
                "sinal_tx_volts",
                "sinal_rx_volts",
            }
            if name in vector_names and hasattr(value, "__len__"):
                length = len(value)
                if length <= TELEMETRY_PREVIEW_ITEMS:
                    return f"{list(value)} (n={length})"
                head = list(value[:TELEMETRY_PREVIEW_ITEMS])
                tail = list(value[-TELEMETRY_PREVIEW_ITEMS:])
                return f"n={length}; inicio={head}; fim={tail}"
            return str(value)

        def _plot_signals(self, signal_tx, signal_rx) -> None:
            """Atualiza os graficos com as amostras reais do simulador."""
            if self.canvas is None:
                return
            self.plot_tx.clear()
            self.plot_rx.clear()
            self.plot_tx.set_title("Sinal TX (V/W)")
            self.plot_rx.set_title("Sinal RX (V/W)")
            if signal_tx is not None and len(signal_tx):
                step_tx = max(1, len(signal_tx) // MAX_PLOT_POINTS)
                self.plot_tx.plot(signal_tx[::step_tx])
            if signal_rx is not None and len(signal_rx):
                step_rx = max(1, len(signal_rx) // MAX_PLOT_POINTS)
                self.plot_rx.plot(signal_rx[::step_rx])
            self.figure.tight_layout()
            self.canvas.draw()

else:

    class ChatWindow:  # pragma: no cover - apenas mensagem de ambiente
        def __init__(self, *_args, **_kwargs):
            require_gtk()


def main() -> None:
    """Ponto de entrada para executar a interface GTK no Linux."""

    require_gtk()
    from gi.repository import Gtk as GtkRuntime

    window = ChatWindow()
    window.connect("destroy", GtkRuntime.main_quit)
    window.show_all()
    GtkRuntime.main()


if __name__ == "__main__":
    main()


__all__ = [
    "ChatController",
    "ChatWindow",
    "DisconnectedLinkAdapter",
    "EnlaceLinkAdapter",
    "SimulatorAdapter",
    "LinkEvent",
    "MessageValidationError",
    "RxPayload",
    "SimulationConfig",
    "TransmissionState",
    "TxPayload",
    "ValidationStatus",
    "decode_message",
    "encode_message",
    "main",
]
