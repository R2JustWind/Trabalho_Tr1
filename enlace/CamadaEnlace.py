# Camada de enlace do simulador

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Tuple

Bits = List[int]


class TipoEnquadramento(Enum):
    CONTAGEM_CARACTERES = "contagem_caracteres"
    ENTRELACAMENTO_BITS = "entrelacamento_bits"
    BYTE_STUFFING = "byte_stuffing"
    BIT_STUFFING = "bit_stuffing"


class TipoControleErro(Enum):
    NENHUM = "nenhum"
    PARIDADE_PAR = "paridade_par"
    CHECKSUM = "checksum"
    CRC32 = "crc32"
    HAMMING = "hamming"


class SituacaoQuadro(Enum):
    OK = "ok"
    CORRIGIDO = "corrigido"
    DESCARTADO = "descartado"


TAMANHOS_CHECKSUM = (8, 16, 32)


# Parâmetros da camada, aceita os enums ou os valores em texto
@dataclass(frozen=True)
class ConfiguracaoEnlace:
    enquadramento: TipoEnquadramento = TipoEnquadramento.CONTAGEM_CARACTERES
    controle_erro: TipoControleErro = TipoControleErro.CRC32
    tamanho_max_quadro: int = 32
    tamanho_checksum: int = 16

    def __post_init__(self) -> None:
        object.__setattr__(self, "enquadramento", TipoEnquadramento(self.enquadramento))
        object.__setattr__(self, "controle_erro", TipoControleErro(self.controle_erro))
        if self.tamanho_max_quadro < 1:
            raise ValueError("tamanho_max_quadro deve ser de pelo menos 1 byte")
        if self.tamanho_checksum not in TAMANHOS_CHECKSUM:
            raise ValueError(f"tamanho_checksum deve ser um de {TAMANHOS_CHECKSUM}")


CONFIGURACAO_PADRAO = ConfiguracaoEnlace()


@dataclass
class QuadroExtraido:
    corpo: Bits
    integro: bool = True


@dataclass
class StatusQuadro:
    indice: int
    situacao: SituacaoQuadro
    detalhe: str = ""


@dataclass
class ResultadoRecepcao:
    payload: Bits
    quadros: List[StatusQuadro] = field(default_factory=list)

    @property
    def houve_descarte(self) -> bool:
        return any(q.situacao is SituacaoQuadro.DESCARTADO for q in self.quadros)


def normalizar_bits(bits: Iterable[int | str]) -> Bits:
    saida = [int(b) for b in bits]
    if any(b not in (0, 1) for b in saida):
        raise ValueError("o fluxo deve conter apenas 0 e 1")
    return saida


def bytes_para_bits(dados: Iterable[int]) -> Bits:
    return [(byte >> deslocamento) & 1 for byte in dados for deslocamento in range(7, -1, -1)]


def bits_para_bytes(bits: Bits) -> List[int]:
    _exigir_multiplo_de_8(bits)
    return [bits_para_inteiro(bits[i:i + 8]) for i in range(0, len(bits), 8)]


def inteiro_para_bits(valor: int, largura: int) -> Bits:
    return [(valor >> deslocamento) & 1 for deslocamento in range(largura - 1, -1, -1)]


def bits_para_inteiro(bits: Bits) -> int:
    valor = 0
    for bit in bits:
        valor = (valor << 1) | bit
    return valor


def _exigir_multiplo_de_8(bits: Bits) -> None:
    if len(bits) % 8:
        raise ValueError(f"esperado múltiplo de 8 bits, recebido {len(bits)}")


def _alinhar_em_bytes(bits: Bits) -> Bits:
    return bits + [0] * (-len(bits) % 8)


# Enquadramento: contagem de caracteres

LIMITE_CONTAGEM = 255


# Cabeçalho de 1 byte com o total de bytes do quadro, contando o próprio cabeçalho
def enquadrar_contagem_caracteres(corpo: Bits) -> Bits:
    _exigir_multiplo_de_8(corpo)
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
    _exigir_multiplo_de_8(corpo)
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


# Detecção de erros: bit de paridade par

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


# Correção de erros: código de Hamming

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
    _exigir_multiplo_de_8(payload)
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


# Rotinas de transmissão e recepção

_ENQUADRADORES: Dict[TipoEnquadramento, Tuple[Callable[[Bits], Bits], Callable[[Bits], List[QuadroExtraido]]]] = {
    TipoEnquadramento.CONTAGEM_CARACTERES: (enquadrar_contagem_caracteres, desenquadrar_contagem_caracteres),
    TipoEnquadramento.ENTRELACAMENTO_BITS: (enquadrar_entrelacamento_bits, desenquadrar_entrelacamento_bits),
    TipoEnquadramento.BYTE_STUFFING: (enquadrar_byte_stuffing, desenquadrar_byte_stuffing),
    TipoEnquadramento.BIT_STUFFING: (enquadrar_bit_stuffing, desenquadrar_bit_stuffing),
}


def _codificar(payload: Bits, config: ConfiguracaoEnlace) -> Bits:
    controle = config.controle_erro
    if controle is TipoControleErro.PARIDADE_PAR:
        return gerar_paridade_par(payload)
    if controle is TipoControleErro.CHECKSUM:
        return gerar_checksum(payload, config.tamanho_checksum)
    if controle is TipoControleErro.CRC32:
        return gerar_crc(payload)
    if controle is TipoControleErro.HAMMING:
        return gerar_hamming(payload)
    return list(payload)


def _validar(corpo: Bits, config: ConfiguracaoEnlace) -> Tuple[Bits, SituacaoQuadro, str]:
    controle = config.controle_erro
    if controle is TipoControleErro.NENHUM:
        return corpo, SituacaoQuadro.OK, ""

    if controle is TipoControleErro.HAMMING:
        payload, corrigidos, valido = corrigir_hamming(corpo)
        if not valido:
            return [], SituacaoQuadro.DESCARTADO, "erro não corrigível pelo Hamming"
        if corrigidos:
            return payload, SituacaoQuadro.CORRIGIDO, f"{corrigidos} bit(s) corrigido(s)"
        return payload, SituacaoQuadro.OK, ""

    if controle is TipoControleErro.PARIDADE_PAR:
        payload, integro = verificar_paridade_par(corpo)
    elif controle is TipoControleErro.CHECKSUM:
        payload, integro = verificar_checksum(corpo, config.tamanho_checksum)
    else:
        payload, integro = verificar_crc(corpo)

    if not integro:
        return [], SituacaoQuadro.DESCARTADO, f"erro detectado ({controle.value})"
    return payload, SituacaoQuadro.OK, ""


# Divide o payload em quadros, anexa o controle de erro, enquadra e devolve para a física
def camada_enlace_transmissora(bits: Iterable[int | str], config: ConfiguracaoEnlace = CONFIGURACAO_PADRAO) -> Bits:
    payload = normalizar_bits(bits)
    _exigir_multiplo_de_8(payload)
    enquadrar, _ = _ENQUADRADORES[config.enquadramento]

    passo = config.tamanho_max_quadro * 8
    fluxo: Bits = []
    for inicio in range(0, len(payload), passo):
        corpo = _alinhar_em_bytes(_codificar(payload[inicio:inicio + passo], config))
        fluxo += enquadrar(corpo)
    return fluxo


# Separa os quadros ignorando o padding, verifica ou corrige e devolve o payload dos quadros aceitos
def camada_enlace_receptora(
    bits: Iterable[int | str], config: ConfiguracaoEnlace = CONFIGURACAO_PADRAO
) -> ResultadoRecepcao:
    fluxo = normalizar_bits(bits)
    _, desenquadrar = _ENQUADRADORES[config.enquadramento]

    resultado = ResultadoRecepcao(payload=[])
    for indice, quadro in enumerate(desenquadrar(fluxo)):
        payload, situacao, detalhe = _validar(quadro.corpo, config)
        if not quadro.integro:
            # Só o Hamming consegue aproveitar um quadro que o enquadramento marcou como suspeito
            pode_corrigir = config.controle_erro is TipoControleErro.HAMMING and quadro.corpo
            if not pode_corrigir or situacao is SituacaoQuadro.DESCARTADO:
                payload, situacao, detalhe = [], SituacaoQuadro.DESCARTADO, "erro detectado no enquadramento"
        resultado.payload += payload
        resultado.quadros.append(StatusQuadro(indice, situacao, detalhe))
    return resultado
