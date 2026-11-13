# Camada de enlace do simulador: ponto de entrada usado pela aplicação e pela camada física

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Tuple

from .bits import (
    Bits,
    alinhar_em_bytes,
    bits_para_bytes,
    bytes_para_bits,
    exigir_multiplo_de_8,
    normalizar_bits,
)
from .correcao import corrigir_hamming, gerar_hamming
from .deteccao import (
    gerar_checksum,
    gerar_crc,
    gerar_paridade_par,
    verificar_checksum,
    verificar_crc,
    verificar_paridade_par,
)
from .enquadramento import (
    QuadroExtraido,
    desenquadrar_bit_stuffing,
    desenquadrar_byte_stuffing,
    desenquadrar_contagem_caracteres,
    desenquadrar_entrelacamento_bits,
    enquadrar_bit_stuffing,
    enquadrar_byte_stuffing,
    enquadrar_contagem_caracteres,
    enquadrar_entrelacamento_bits,
)

__all__ = [
    "Bits",
    "ConfiguracaoEnlace",
    "ResultadoRecepcao",
    "SituacaoQuadro",
    "StatusQuadro",
    "TipoControleErro",
    "TipoEnquadramento",
    "bits_para_bytes",
    "bytes_para_bits",
    "camada_enlace_receptora",
    "camada_enlace_transmissora",
]


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
    exigir_multiplo_de_8(payload)
    enquadrar, _ = _ENQUADRADORES[config.enquadramento]

    passo = config.tamanho_max_quadro * 8
    fluxo: Bits = []
    for inicio in range(0, len(payload), passo):
        corpo = alinhar_em_bytes(_codificar(payload[inicio:inicio + passo], config))
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
