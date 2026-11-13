"""Conversão pertencente à camada de aplicação: texto <-> bytes."""

from __future__ import annotations


DEFAULT_ENCODING = "utf-8"


class MessageValidationError(ValueError):
    """Entrada que não pode ser enviada ou decodificada como texto."""


def encode_message(text: str, *, encoding: str = DEFAULT_ENCODING) -> bytes:
    if not isinstance(text, str):
        raise MessageValidationError("A mensagem precisa ser texto.")
    if not text.strip():
        raise MessageValidationError("Digite uma mensagem antes de enviar.")
    try:
        return text.encode(encoding)
    except UnicodeEncodeError as exc:
        raise MessageValidationError(
            f"A mensagem não pode ser convertida com {encoding}."
        ) from exc


def decode_message(payload: bytes, *, encoding: str = DEFAULT_ENCODING) -> str:
    if not isinstance(payload, bytes):
        raise MessageValidationError("O payload recebido precisa ser bytes.")
    try:
        return payload.decode(encoding)
    except UnicodeDecodeError as exc:
        raise MessageValidationError(
            f"O payload não é texto válido em {encoding}."
        ) from exc
