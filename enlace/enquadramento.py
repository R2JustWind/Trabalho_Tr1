# Enquadramento: contagem de caracteres, entrelaçamento de bits, byte stuffing e bit stuffing

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .bits import Bits, bits_para_bytes, bits_para_inteiro, bytes_para_bits, exigir_multiplo_de_8, inteiro_para_bits


# Quadro separado pelo receptor, integro=False quando o próprio enquadramento percebeu erro
@dataclass
class QuadroExtraido:
    corpo: Bits
    integro: bool = True


LIMITE_CONTAGEM = 255


# Cabeçalho de 1 byte com o total de bytes do quadro, contando o próprio cabeçalho
def enquadrar_contagem_caracteres(corpo: Bits) -> Bits:
    exigir_multiplo_de_8(corpo)
    contagem = len(corpo) // 8 + 1
    if contagem > LIMITE_CONTAGEM:
        raise ValueError(f"quadro de {contagem} bytes excede o limite de {LIMITE_CONTAGEM}")
    return inteiro_para_bits(contagem, 8) + corpo


def desenquadrar_contagem_caracteres(fluxo: Bits) -> List[QuadroExtraido]:
    quadros: List[QuadroExtraido] = []
    inicio = 0
    while inicio + 8 <= len(fluxo):
        contagem = bits_para_inteiro(fluxo[inicio:inicio + 8])
        if contagem == 0:
            break  # contagem 0 só aparece no padding da camada física
        fim = inicio + contagem * 8
        if fim > len(fluxo):
            quadros.append(QuadroExtraido([], integro=False))
            break
        if contagem > 1:
            quadros.append(QuadroExtraido(fluxo[inicio + 8:fim]))
        inicio = fim
    return quadros


# Enquadramento: entrelaçamento de bits

LARGURA_LINHA_ENTRELACAMENTO = 8
LIMITE_LINHAS_ENTRELACAMENTO = 255


def _paridades_das_colunas(corpo: Bits) -> Bits:
    largura = LARGURA_LINHA_ENTRELACAMENTO
    return [sum(corpo[coluna::largura]) % 2 for coluna in range(largura)]


# Corpo em linhas de 8 bits e uma última linha com a paridade par de cada coluna, detecta rajadas de até 8 bits
def enquadrar_entrelacamento_bits(corpo: Bits) -> Bits:
    exigir_multiplo_de_8(corpo)
    linhas = len(corpo) // LARGURA_LINHA_ENTRELACAMENTO
    if not 0 < linhas <= LIMITE_LINHAS_ENTRELACAMENTO:
        raise ValueError(f"quadro com {linhas} linhas fora do limite de {LIMITE_LINHAS_ENTRELACAMENTO}")
    return inteiro_para_bits(linhas, 8) + corpo + _paridades_das_colunas(corpo)


def desenquadrar_entrelacamento_bits(fluxo: Bits) -> List[QuadroExtraido]:
    largura = LARGURA_LINHA_ENTRELACAMENTO
    quadros: List[QuadroExtraido] = []
    inicio = 0
    while inicio + 8 <= len(fluxo):
        linhas = bits_para_inteiro(fluxo[inicio:inicio + 8])
        if linhas == 0:
            break
        inicio_corpo = inicio + 8
        fim_corpo = inicio_corpo + linhas * largura
        fim = fim_corpo + largura
        if fim > len(fluxo):
            quadros.append(QuadroExtraido([], integro=False))
            break
        corpo = fluxo[inicio_corpo:fim_corpo]
        integro = _paridades_das_colunas(corpo) == fluxo[fim_corpo:fim]
        quadros.append(QuadroExtraido(corpo, integro))
        inicio = fim
    return quadros


# Enquadramento: bytes de flag com inserção de bytes

FLAG_BYTE = 0x7E
ESC_BYTE = 0x7D


# FLAG + corpo + FLAG, com um ESC antes de cada FLAG ou ESC que aparecer no corpo
def enquadrar_byte_stuffing(corpo: Bits) -> Bits:
    saida = [FLAG_BYTE]
    for byte in bits_para_bytes(corpo):
        if byte in (FLAG_BYTE, ESC_BYTE):
            saida.append(ESC_BYTE)
        saida.append(byte)
    saida.append(FLAG_BYTE)
    return bytes_para_bits(saida)


def desenquadrar_byte_stuffing(fluxo: Bits) -> List[QuadroExtraido]:
    dados = bits_para_bytes(fluxo[:len(fluxo) - len(fluxo) % 8])
    quadros: List[QuadroExtraido] = []
    atual: List[int] | None = None
    escapando = False

    for byte in dados:
        if atual is None:
            if byte == FLAG_BYTE:
                atual = []
            continue
        if escapando:
            atual.append(byte)
            escapando = False
        elif byte == ESC_BYTE:
            escapando = True
        elif byte == FLAG_BYTE:
            if atual:
                quadros.append(QuadroExtraido(bytes_para_bits(atual)))
                atual = None
            # duas flags seguidas: fim de um quadro e início do próximo
        else:
            atual.append(byte)

    if atual:
        quadros.append(QuadroExtraido([], integro=False))
    return quadros


# Enquadramento: flags com inserção de bits

FLAG_BITS = [0, 1, 1, 1, 1, 1, 1, 0]
LIMITE_UNS_CONSECUTIVOS = 5


def _buscar_flag(fluxo: Bits, inicio: int) -> int:
    for posicao in range(inicio, len(fluxo) - len(FLAG_BITS) + 1):
        if fluxo[posicao:posicao + len(FLAG_BITS)] == FLAG_BITS:
            return posicao
    return -1


# Flag 01111110 nas pontas e um 0 inserido depois de cada sequência de cinco 1s
def enquadrar_bit_stuffing(corpo: Bits) -> Bits:
    saida = list(FLAG_BITS)
    uns = 0
    for bit in corpo:
        saida.append(bit)
        uns = uns + 1 if bit else 0
        if uns == LIMITE_UNS_CONSECUTIVOS:
            saida.append(0)
            uns = 0
    return saida + FLAG_BITS


def desenquadrar_bit_stuffing(fluxo: Bits) -> List[QuadroExtraido]:
    quadros: List[QuadroExtraido] = []
    abertura = _buscar_flag(fluxo, 0)

    while abertura != -1:
        posicao = abertura + len(FLAG_BITS)
        corpo: Bits = []
        uns = 0
        fechamento = -1
        violacao = False

        while posicao + len(FLAG_BITS) <= len(fluxo):
            if fluxo[posicao:posicao + len(FLAG_BITS)] == FLAG_BITS:
                fechamento = posicao
                break
            bit = fluxo[posicao]
            posicao += 1
            if uns == LIMITE_UNS_CONSECUTIVOS:
                uns = 0
                if bit == 0:
                    continue  # 0 inserido pelo transmissor
                violacao = True  # seis 1s fora de uma flag só aparecem com erro no canal
                break
            corpo.append(bit)
            uns = uns + 1 if bit else 0

        if violacao:
            quadros.append(QuadroExtraido([], integro=False))
            abertura = _buscar_flag(fluxo, posicao)
        elif fechamento == -1:
            if corpo:
                quadros.append(QuadroExtraido([], integro=False))
            break
        elif corpo:
            quadros.append(QuadroExtraido(corpo))
            abertura = _buscar_flag(fluxo, fechamento + len(FLAG_BITS))
        else:
            abertura = fechamento
    return quadros
