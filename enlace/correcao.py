# Correção de erros: código de Hamming

from __future__ import annotations

from typing import Tuple

from .bits import Bits, exigir_multiplo_de_8

BITS_DADOS_HAMMING = 8


def _bits_verificacao_hamming(bits_dados: int) -> int:
    r = 0
    while 2 ** r < bits_dados + r + 1:
        r += 1
    return r


# Posições contadas a partir de 1, as potências de 2 são bits de verificação com paridade par
def codificar_hamming(dados: Bits) -> Bits:
    n = len(dados) + _bits_verificacao_hamming(len(dados))
    palavra = [0] * (n + 1)
    restantes = iter(dados)
    for posicao in range(1, n + 1):
        if posicao & (posicao - 1):
            palavra[posicao] = next(restantes)
    verificacao = 1
    while verificacao <= n:
        palavra[verificacao] = sum(palavra[p] for p in range(1, n + 1) if p & verificacao) % 2
        verificacao <<= 1
    return palavra[1:]


# A síndrome (XOR das posições com bit 1) é a posição do bit errado, 0 quando não há erro
def decodificar_hamming(palavra: Bits) -> Tuple[Bits, int, bool]:
    sindrome = 0
    for posicao, bit in enumerate(palavra, start=1):
        if bit:
            sindrome ^= posicao
    if sindrome > len(palavra):
        return [], 0, False
    palavra = list(palavra)
    if sindrome:
        palavra[sindrome - 1] ^= 1
    dados = [bit for posicao, bit in enumerate(palavra, start=1) if posicao & (posicao - 1)]
    return dados, sindrome, True


TAMANHO_PALAVRA_HAMMING = BITS_DADOS_HAMMING + _bits_verificacao_hamming(BITS_DADOS_HAMMING)


# Hamming(12, 8) em cada byte, corrige um erro por byte
def gerar_hamming(payload: Bits) -> Bits:
    exigir_multiplo_de_8(payload)
    saida: Bits = []
    for i in range(0, len(payload), BITS_DADOS_HAMMING):
        saida += codificar_hamming(payload[i:i + BITS_DADOS_HAMMING])
    return saida


# Bits depois da última palavra completa são alinhamento
def corrigir_hamming(corpo: Bits) -> Tuple[Bits, int, bool]:
    payload: Bits = []
    corrigidos = 0
    total = len(corpo) // TAMANHO_PALAVRA_HAMMING
    for i in range(total):
        palavra = corpo[i * TAMANHO_PALAVRA_HAMMING:(i + 1) * TAMANHO_PALAVRA_HAMMING]
        dados, posicao_erro, valido = decodificar_hamming(palavra)
        if not valido:
            return [], corrigidos, False
        payload += dados
        corrigidos += posicao_erro != 0
    return payload, corrigidos, total > 0
