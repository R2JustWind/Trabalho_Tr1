# Simulador: rotina principal que liga aplicação, enlace, física e meio, com transmissor e receptor em threads separadas

from __future__ import annotations

import threading
import queue
import time
import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from InterfaceGUI import encode_message
from fisica.CamadaFisica import CONFIG_PADRAO, fisica_rx, fisica_tx

from enlace.CamadaEnlace import (
    ConfiguracaoEnlace,
    ResultadoRecepcao,
    bits_para_bytes,
    bytes_para_bits,
    camada_enlace_receptora,
    camada_enlace_transmissora,
)

from .canal import MeioComunicacao, Sinal

Bits = List[int]
FisicaTransmissora = Callable[[Bits], Sinal]
FisicaReceptora = Callable[[Sinal], Bits]


@dataclass(frozen=True)
class ConfiguracaoSimulacao:
    enlace: ConfiguracaoEnlace = field(default_factory=ConfiguracaoEnlace)
    media_ruido: float = 0.0
    desvio_ruido: float = 0.0
    semente_ruido: Optional[int] = None
    codificacao: str = "utf-8"
    tempo_limite: float = 30.0
    fisica: dict = field(default_factory=lambda: dict(CONFIG_PADRAO))


# Guarda a saída de cada etapa para a interface mostrar e plotar
@dataclass
class ResultadoSimulacao:
    texto_enviado: str
    bits_aplicacao: Bits = field(default_factory=list)
    bits_enlace_tx: Bits = field(default_factory=list)
    sinal_tx: Sinal = field(default_factory=list)
    sinal_rx: Sinal = field(default_factory=list)
    bits_fisica_rx: Bits = field(default_factory=list)
    recepcao_enlace: ResultadoRecepcao = field(default_factory=lambda: ResultadoRecepcao(payload=[]))
    texto_recebido: str = ""


class Simulador:
    def __init__(
        self,
        config: ConfiguracaoSimulacao = ConfiguracaoSimulacao(),
        fisica_transmissora: FisicaTransmissora | None = None,
        fisica_receptora: FisicaReceptora | None = None,
    ):
        self.config = config
        if not isinstance(self.config.tempo_limite, (int, float)) or not math.isfinite(self.config.tempo_limite):
            raise ValueError("tempo_limite precisa ser finito")
        if self.config.tempo_limite <= 0:
            raise ValueError("tempo_limite precisa ser maior que zero")
        self.fisica_transmissora = fisica_transmissora or self._fisica_transmissora_real
        self.fisica_receptora = fisica_receptora or self._fisica_receptora_real

    def _fisica_transmissora_real(self, bits: Bits) -> Sinal:
        return fisica_tx(bits, self.config.fisica)["sinal"].tolist()

    def _fisica_receptora_real(self, sinal: Sinal) -> Bits:
        return fisica_rx(sinal, self.config.fisica)["bits"]

    def enviar(self, texto: str) -> ResultadoSimulacao:
        meio = MeioComunicacao(self.config.media_ruido, self.config.desvio_ruido, self.config.semente_ruido)
        resultado = ResultadoSimulacao(texto_enviado=texto)
        erros: List[BaseException] = []

        transmissor = threading.Thread(target=self._executar_transmissor, args=(texto, meio, resultado, erros), name="TX", daemon=True)
        receptor = threading.Thread(target=self._executar_receptor, args=(meio, resultado, erros), name="RX", daemon=True)
        receptor.start()
        transmissor.start()
        inicio = time.monotonic()
        transmissor.join(self.config.tempo_limite)
        restante = self.config.tempo_limite - (time.monotonic() - inicio)
        if restante > 0:
            receptor.join(restante)

        if erros:
            raise erros[0]
        if transmissor.is_alive() or receptor.is_alive():
            meio.encerrar()
            raise TimeoutError("a simulação excedeu o tempo limite e foi interrompida")
        return resultado

    def _executar_transmissor(self, texto: str, meio: MeioComunicacao, resultado: ResultadoSimulacao,
                              erros: List[BaseException]) -> None:
        try:
            resultado.bits_aplicacao = bytes_para_bits(encode_message(texto, encoding=self.config.codificacao))
            resultado.bits_enlace_tx = camada_enlace_transmissora(resultado.bits_aplicacao, self.config.enlace)
            resultado.sinal_tx = self.fisica_transmissora(resultado.bits_enlace_tx)
            meio.enviar(resultado.sinal_tx)
        except Exception as erro:
            erros.append(erro)
            meio.encerrar()

    def _executar_receptor(self, meio: MeioComunicacao, resultado: ResultadoSimulacao,
                           erros: List[BaseException]) -> None:
        try:
            sinal = meio.receber(self.config.tempo_limite)
            if sinal is None:
                return
            resultado.sinal_rx = sinal
            resultado.bits_fisica_rx = self.fisica_receptora(sinal)
            resultado.recepcao_enlace = camada_enlace_receptora(resultado.bits_fisica_rx, self.config.enlace)
            if resultado.recepcao_enlace.houve_descarte:
                # Não expõe texto parcial: a aplicação só deve receber payload validado.
                resultado.texto_recebido = ""
            else:
                payload = bytes(bits_para_bytes(resultado.recepcao_enlace.payload))
                try:
                    resultado.texto_recebido = payload.decode(self.config.codificacao)
                except UnicodeDecodeError:
                    # Bits recuperados podem ainda não formar texto válido.
                    resultado.texto_recebido = ""
        except queue.Empty as erro:
            erros.append(TimeoutError("o receptor não recebeu sinal dentro do tempo limite"))
            meio.encerrar()
        except Exception as erro:
            erros.append(erro)
