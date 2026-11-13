# Simulador: rotina principal que liga aplicação, enlace, física e meio, com transmissor e receptor em threads separadas

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from interface.codec import encode_message

from enlace.CamadaEnlace import (
    ConfiguracaoEnlace,
    ResultadoRecepcao,
    bits_para_bytes,
    bytes_para_bits,
    camada_enlace_receptora,
    camada_enlace_transmissora,
)

from . import fisica_provisoria
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
        fisica_transmissora: FisicaTransmissora = fisica_provisoria.camada_fisica_transmissora,
        fisica_receptora: FisicaReceptora = fisica_provisoria.camada_fisica_receptora,
    ):
        self.config = config
        self.fisica_transmissora = fisica_transmissora
        self.fisica_receptora = fisica_receptora

    def enviar(self, texto: str) -> ResultadoSimulacao:
        meio = MeioComunicacao(self.config.media_ruido, self.config.desvio_ruido, self.config.semente_ruido)
        resultado = ResultadoSimulacao(texto_enviado=texto)
        erros: List[BaseException] = []

        transmissor = threading.Thread(target=self._executar_transmissor, args=(texto, meio, resultado, erros), name="TX")
        receptor = threading.Thread(target=self._executar_receptor, args=(meio, resultado, erros), name="RX")
        receptor.start()
        transmissor.start()
        transmissor.join(self.config.tempo_limite)
        receptor.join(self.config.tempo_limite)

        if erros:
            raise erros[0]
        if transmissor.is_alive() or receptor.is_alive():
            raise TimeoutError("a simulação passou do tempo limite")
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
            payload = bytes(bits_para_bytes(resultado.recepcao_enlace.payload))
            # Se um quadro foi descartado a mensagem chega incompleta e pode cortar um caractere UTF-8 no meio
            resultado.texto_recebido = payload.decode(self.config.codificacao, errors="replace")
        except Exception as erro:
            erros.append(erro)
