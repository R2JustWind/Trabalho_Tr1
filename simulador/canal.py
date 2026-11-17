# Meio de comunicação: liga a thread TX à thread RX e soma ruído gaussiano n(média, σ) a cada amostra em volts

from __future__ import annotations

import queue
import random
import math
from typing import List, Optional

Sinal = List[float]


class MeioComunicacao:
    def __init__(self, media: float = 0.0, desvio_padrao: float = 0.0, semente: Optional[int] = None):
        try:
            media = float(media)
            desvio_padrao = float(desvio_padrao)
        except (TypeError, ValueError) as erro:
            raise ValueError("média e desvio padrão precisam ser números") from erro
        if not math.isfinite(media) or not math.isfinite(desvio_padrao):
            raise ValueError("média e desvio padrão precisam ser finitos")
        if desvio_padrao < 0:
            raise ValueError("o desvio padrão do ruído não pode ser negativo")
        self.media = media
        self.desvio_padrao = desvio_padrao
        self._gerador = random.Random(semente)
        self._fila: "queue.Queue[Optional[Sinal]]" = queue.Queue()

    def aplicar_ruido(self, sinal: Sinal) -> Sinal:
        if any(not math.isfinite(float(amostra)) for amostra in sinal):
            raise ValueError("o sinal precisa conter somente amostras finitas")
        return [amostra + self._gerador.gauss(self.media, self.desvio_padrao) for amostra in sinal]

    def enviar(self, sinal: Sinal) -> None:
        self._fila.put(self.aplicar_ruido(sinal))

    # Avisa o receptor que nada mais vai chegar, usado quando o transmissor falha
    def encerrar(self) -> None:
        self._fila.put(None)

    def receber(self, tempo_limite: Optional[float] = None) -> Optional[Sinal]:
        return self._fila.get(timeout=tempo_limite)
