"""View GTK3 da aplicação de chat.

Importar este módulo não exige GTK, permitindo testar o núcleo em ambientes
sem display. Executar a GUI requer PyGObject/GTK3 já instalado no Linux.
"""

from __future__ import annotations

from .adapter import EnlaceLinkAdapter
from .controller import ChatController
from .models import RxPayload, SimulationConfig, ValidationStatus

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
except ImportError:  # pragma: no cover - depende do ambiente gráfico Linux
    Gtk = None


METHODS = {
    "framing": ["contagem de caracteres", "entrelaçamento de bits", "byte stuffing", "bit stuffing"],
    "error": ["paridade par", "checksum", "CRC-32", "Hamming"],
    "baseband": ["NRZ-Polar", "Manchester", "Bipolar"],
    "carrier": ["ASK", "FSK", "8PSK", "32-QAM"],
}


def require_gtk() -> None:
    if Gtk is None:
        raise RuntimeError("GTK3/PyGObject não está instalado neste ambiente Linux.")


if Gtk is not None:  # pragma: no cover - requer display e GTK no ambiente de teste

    class ChatWindow(Gtk.Window):
        def __init__(self, controller: ChatController | None = None):
            super().__init__(title="TR1 — Chat de Teleinformática")
            self.set_default_size(900, 650)
            self.controller = controller or ChatController(EnlaceLinkAdapter())
            self._build()

        def _build(self) -> None:
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            root.set_border_width(12)
            self.add(root)

            title = Gtk.Label(label="Aplicação de rede — Chat TX/RX")
            title.set_xalign(0)
            root.pack_start(title, False, False, 0)

            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            root.pack_start(content, True, True, 0)
            content.pack_start(self._build_tx(), True, True, 0)
            content.pack_start(self._build_rx(), True, True, 0)
            root.pack_start(self._build_config(), False, False, 0)
            root.pack_start(self._build_telemetry(), True, True, 0)

        def _frame(self, title: str) -> tuple[Gtk.Frame, Gtk.Box]:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_border_width(8)
            frame = Gtk.Frame(label=title)
            frame.add(box)
            return frame, box

        def _build_tx(self) -> Gtk.Widget:
            frame, box = self._frame("TX — Transmissor")
            self.input = Gtk.Entry()
            self.input.set_placeholder_text("Digite a mensagem")
            box.pack_start(self.input, False, False, 0)
            send = Gtk.Button(label="Enviar")
            send.connect("clicked", self._send)
            box.pack_start(send, False, False, 0)
            return frame

        def _build_rx(self) -> Gtk.Widget:
            frame, box = self._frame("RX — Receptor")
            self.received = Gtk.Label(label="Nenhuma mensagem recebida.")
            self.received.set_xalign(0)
            self.received.set_line_wrap(True)
            box.pack_start(self.received, True, True, 0)
            return frame

        def _combo(self, values: list[str], default: str) -> Gtk.ComboBoxText:
            combo = Gtk.ComboBoxText()
            for value in values:
                combo.append_text(value)
            combo.set_active(values.index(default))
            return combo

        def _build_config(self) -> Gtk.Widget:
            frame, grid_box = self._frame("Configuração geral")
            grid = Gtk.Grid(column_spacing=8, row_spacing=5)
            grid_box.pack_start(grid, False, False, 0)
            self.controls: dict[str, Gtk.Widget] = {}
            fields = [
                ("Enquadramento", "framing", METHODS["framing"]),
                ("Detecção/correção", "error", METHODS["error"]),
                ("Modulação banda-base", "baseband", METHODS["baseband"]),
                ("Modulação portadora", "carrier", METHODS["carrier"]),
            ]
            for row, (label, key, values) in enumerate(fields):
                grid.attach(Gtk.Label(label=label), 0, row, 1, 1)
                combo = self._combo(values, values[0])
                self.controls[key] = combo
                grid.attach(combo, 1, row, 1, 1)
            for row, (label, key, default) in enumerate(
                [("Tamanho máximo do quadro", "frame_size", "1024"), ("Tamanho do EDC", "edc_size", "0"),
                 ("Média AWGN (V/W)", "noise_mean", "0"), ("Desvio AWGN (V/W)", "noise_std", "0")], start=4
            ):
                grid.attach(Gtk.Label(label=label), 0, row, 1, 1)
                entry = Gtk.Entry(); entry.set_text(default)
                self.controls[key] = entry
                grid.attach(entry, 1, row, 1, 1)
            return frame

        def _build_telemetry(self) -> Gtk.Widget:
            frame, box = self._frame("Status e telemetria")
            self.status = Gtk.Label(label="UNAVAILABLE — aguardando integração")
            self.status.set_xalign(0)
            box.pack_start(self.status, False, False, 0)
            self.telemetry = Gtk.TextView(); self.telemetry.set_editable(False)
            self.telemetry.get_buffer().set_text("Bits e amostras: resultado indisponível até o backend fornecer dados.")
            box.pack_start(self.telemetry, True, True, 0)
            return frame

        def _config(self) -> SimulationConfig:
            def integer(key: str) -> int:
                value = int(self.controls[key].get_text())
                if value < 0: raise ValueError("valores inteiros não podem ser negativos")
                return value
            config = SimulationConfig(
                frame_size=integer("frame_size"), edc_size=integer("edc_size"),
                framing_method=self.controls["framing"].get_active_text(),
                error_control_method=self.controls["error"].get_active_text(),
                baseband_modulation=self.controls["baseband"].get_active_text(),
                carrier_modulation=self.controls["carrier"].get_active_text(),
                noise_mean=float(self.controls["noise_mean"].get_text()),
                noise_standard_deviation=float(self.controls["noise_std"].get_text()),
            )
            if config.frame_size == 0:
                raise ValueError("o tamanho máximo do quadro deve ser maior que zero")
            return config

        def _send(self, _button: Gtk.Button) -> None:
            try:
                configuration = self._config()
                if configuration.noise_standard_deviation < 0:
                    raise ValueError("o desvio padrão não pode ser negativo")
            except ValueError as exc:
                self.status.set_text(f"FAILED — configuração inválida: {exc}")
                return
            self.controller.send(self.input.get_text(), configuration, self._event)

        def present_received(self, payload: RxPayload) -> None:
            """Apresenta somente payload com validação explícita do backend."""
            text = self.controller.receive(payload, self._event)
            if text is not None:
                self.received.set_text(text)

        def _event(self, event) -> None:
            self.status.set_text(f"{event.state.value} — {event.detail or 'sem detalhe'}")
            if event.telemetry:
                lines = []
                for name, value in event.telemetry.items():
                    lines.append(f"{name}: {value}")
                self.telemetry.get_buffer().set_text("\n".join(lines))

else:

    class ChatWindow:  # pragma: no cover - apenas mensagem de ambiente
        def __init__(self, *_args, **_kwargs):
            require_gtk()
