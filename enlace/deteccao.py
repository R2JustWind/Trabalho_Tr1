# Detecção de erros: bit de paridade par, checksum e CRC-32

from __future__ import annotations

from typing import Tuple

from .bits import Bits, bits_para_inteiro, inteiro_para_bits


def gerar_paridade_par(payload: Bits) -> Bits:
    return payload + [sum(payload) % 2]


# O bit logo após o payload é a paridade, o que vem depois é alinhamento
def verificar_paridade_par(corpo: Bits) -> Tuple[Bits, bool]:
    if not corpo:
        return [], False
    tamanho_payload = (len(corpo) - 1) // 8 * 8
    payload = corpo[:tamanho_payload]
    return payload, sum(payload) % 2 == corpo[tamanho_payload]


# Detecção de erros: checksum

# Soma em segmentos de n bits, o vai-um que sai do bit mais alto volta para o bit 0
def _soma_complemento_de_um(bits: Bits, largura: int) -> int:
    mascara = (1 << largura) - 1
    segmentos = bits + [0] * (-len(bits) % largura)
    soma = 0
    for i in range(0, len(segmentos), largura):
        soma += bits_para_inteiro(segmentos[i:i + largura])
        soma = (soma & mascara) + (soma >> largura)
    return soma


# Anexa o complemento da soma dos segmentos
def gerar_checksum(payload: Bits, largura: int = 16) -> Bits:
    mascara = (1 << largura) - 1
    checksum = ~_soma_complemento_de_um(payload, largura) & mascara
    return payload + inteiro_para_bits(checksum, largura)


# Soma os segmentos recebidos com o checksum, o complemento do total tem que dar zero
def verificar_checksum(corpo: Bits, largura: int = 16) -> Tuple[Bits, bool]:
    tamanho_payload = len(corpo) - largura
    tamanho_payload -= tamanho_payload % 8
    if tamanho_payload < 0:
        return [], False
    payload = corpo[:tamanho_payload]
    recebido = bits_para_inteiro(corpo[tamanho_payload:tamanho_payload + largura])
    mascara = (1 << largura) - 1
    soma = _soma_complemento_de_um(payload, largura) + recebido
    soma = (soma & mascara) + (soma >> largura)
    return payload, ~soma & mascara == 0


# Detecção de erros: CRC-32

# G(x) = x^32 + x^26 + x^23 + x^22 + x^16 + x^12 + x^11 + x^10 + x^8 + x^7 + x^5 + x^4 + x^2 + x + 1 (IEEE 802)
GERADOR_CRC32 = inteiro_para_bits(0x104C11DB7, 33)


# Divisão módulo 2: XOR com o gerador quando o bit mais à esquerda é 1
def resto_divisao_polinomial(dividendo: Bits, gerador: Bits) -> Bits:
    resto = list(dividendo)
    grau = len(gerador) - 1
    for i in range(len(resto) - grau):
        if resto[i]:
            for j, bit in enumerate(gerador):
                resto[i + j] ^= bit
    return resto[-grau:]


# Anexa r zeros, divide por G e coloca o resto no lugar dos zeros
def gerar_crc(payload: Bits, gerador: Bits = GERADOR_CRC32) -> Bits:
    grau = len(gerador) - 1
    return payload + resto_divisao_polinomial(payload + [0] * grau, gerador)


# Divide o quadro recebido por G, resto diferente de zero indica erro
def verificar_crc(corpo: Bits, gerador: Bits = GERADOR_CRC32) -> Tuple[Bits, bool]:
    grau = len(gerador) - 1
    if len(corpo) <= grau:
        return [], False
    return corpo[:-grau], not any(resto_divisao_polinomial(corpo, gerador))
