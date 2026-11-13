# Camada física provisória em NRZ-Polar, só para o simulador rodar até a camada física do Arthur ficar pronta

from __future__ import annotations

from typing import List

from .canal import Sinal

TENSAO = 1.0
AMOSTRAS_POR_BIT = 8
BITS_POR_SIMBOLO = 3


# Completa com zeros até fechar um símbolo, como o 8PSK vai fazer, para exercitar o padding no receptor
def camada_fisica_transmissora(bits: List[int]) -> Sinal:
    completos = bits + [0] * (-len(bits) % BITS_POR_SIMBOLO)
    return [TENSAO if bit else -TENSAO for bit in completos for _ in range(AMOSTRAS_POR_BIT)]


# Cada bit é decidido pela média das amostras do seu intervalo, com limiar em 0 V
def camada_fisica_receptora(sinal: Sinal) -> List[int]:
    return [
        1 if sum(sinal[i:i + AMOSTRAS_POR_BIT]) > 0 else 0
        for i in range(0, len(sinal) - AMOSTRAS_POR_BIT + 1, AMOSTRAS_POR_BIT)
    ]
