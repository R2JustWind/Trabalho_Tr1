# Conversões entre bits, bytes e inteiros usadas por toda a camada de enlace

from __future__ import annotations

from typing import Iterable, List

Bits = List[int]


def normalizar_bits(bits: Iterable[int | str]) -> Bits:
    saida = [int(b) for b in bits]
    if any(b not in (0, 1) for b in saida):
        raise ValueError("o fluxo deve conter apenas 0 e 1")
    return saida


def bytes_para_bits(dados: Iterable[int]) -> Bits:
    return [(byte >> deslocamento) & 1 for byte in dados for deslocamento in range(7, -1, -1)]


def bits_para_bytes(bits: Bits) -> List[int]:
    exigir_multiplo_de_8(bits)
    return [bits_para_inteiro(bits[i:i + 8]) for i in range(0, len(bits), 8)]


def inteiro_para_bits(valor: int, largura: int) -> Bits:
    return [(valor >> deslocamento) & 1 for deslocamento in range(largura - 1, -1, -1)]


def bits_para_inteiro(bits: Bits) -> int:
    valor = 0
    for bit in bits:
        valor = (valor << 1) | bit
    return valor


def exigir_multiplo_de_8(bits: Bits) -> None:
    if len(bits) % 8:
        raise ValueError(f"esperado múltiplo de 8 bits, recebido {len(bits)}")


def alinhar_em_bytes(bits: Bits) -> Bits:
    return bits + [0] * (-len(bits) % 8)
