import random
import unittest

from enlace.bits import bits_para_bytes, bytes_para_bits
from enlace.CamadaEnlace import (
    TAMANHOS_CHECKSUM,
    ConfiguracaoEnlace,
    TipoControleErro,
    TipoEnquadramento,
    camada_enlace_receptora,
    camada_enlace_transmissora,
)
from enlace.correcao import codificar_hamming, decodificar_hamming
from enlace.deteccao import gerar_checksum, gerar_crc, gerar_paridade_par, verificar_checksum, verificar_crc
from enlace.enquadramento import (
    ESC_BYTE,
    FLAG_BYTE,
    enquadrar_bit_stuffing,
    enquadrar_byte_stuffing,
    enquadrar_contagem_caracteres,
)


def bits(texto):
    return [int(c) for c in texto.replace(" ", "")]


def texto(lista):
    return "".join(map(str, lista))


def aleatorio(n, semente=7):
    gerador = random.Random(semente + n)
    return bytes(gerador.randrange(256) for _ in range(n))


def inverter(fluxo, *posicoes):
    copia = list(fluxo)
    for posicao in posicoes:
        copia[posicao] ^= 1
    return copia


class ExemplosDosSlides(unittest.TestCase):
    def test_paridade_par(self):
        self.assertEqual(texto(gerar_paridade_par(bits("0101101"))), "01011010")

    def test_checksum_de_8_bits(self):
        self.assertEqual(texto(gerar_checksum(bits("10101001 00111001"), 8))[-8:], "00011101")
        self.assertTrue(verificar_checksum(bits("10101001 00111001 00011101"), 8)[1])

    def test_crc_com_gerador_1101(self):
        self.assertEqual(texto(gerar_crc(bits("100100"), bits("1101"))), "100100001")
        self.assertTrue(verificar_crc(bits("100100001"), bits("1101"))[1])
        self.assertFalse(verificar_crc(bits("100101001"), bits("1101"))[1])

    def test_hamming_11_7_exemplo_1(self):
        self.assertEqual(texto(codificar_hamming(bits("1101001"))), "01101011001")
        dados, posicao, valido = decodificar_hamming(bits("01100011001"))
        self.assertEqual((texto(dados), posicao, valido), ("1101001", 5, True))

    def test_hamming_11_7_exemplo_2(self):
        palavra = codificar_hamming(bits("1001110"))
        self.assertEqual(texto(palavra), "11110010110")
        dados, posicao, _ = decodificar_hamming(inverter(palavra, 6))
        self.assertEqual((texto(dados), posicao), ("1001110", 7))

    def test_bit_stuffing(self):
        quadro = texto(enquadrar_bit_stuffing(bits("011011111111111111110010")))
        self.assertEqual(quadro[8:-8], "011011111011111011111010010")

    def test_byte_stuffing(self):
        quadro = bits_para_bytes(enquadrar_byte_stuffing(bytes_para_bits([1, ESC_BYTE, FLAG_BYTE, 3])))
        self.assertEqual(quadro, [FLAG_BYTE, 1, ESC_BYTE, ESC_BYTE, ESC_BYTE, FLAG_BYTE, 3, FLAG_BYTE])

    def test_contagem_inclui_o_cabecalho(self):
        self.assertEqual(bits_para_bytes(enquadrar_contagem_caracteres(bytes_para_bits([1, 2]))), [3, 1, 2])


class IdaEVolta(unittest.TestCase):
    MENSAGENS = [b"", b"a", "Olá, TR1!".encode(), bytes([FLAG_BYTE, ESC_BYTE, 0xFF, 0x00] * 20),
                 aleatorio(300), b"\xff" * 100, b"\x00" * 50]

    def test_todas_as_combinacoes_com_padding_da_fisica(self):
        for enquadramento in TipoEnquadramento:
            for controle in TipoControleErro:
                larguras = TAMANHOS_CHECKSUM if controle is TipoControleErro.CHECKSUM else (16,)
                for largura in larguras:
                    for tamanho in (1, 7, 32, 64):
                        config = ConfiguracaoEnlace(enquadramento, controle, tamanho, largura)
                        for mensagem in self.MENSAGENS:
                            tx = camada_enlace_transmissora(bytes_para_bits(mensagem), config)
                            for padding in (0, 1, 2, 4, 7, 8, 13, 40):
                                with self.subTest(config=config, tamanho_msg=len(mensagem), padding=padding):
                                    rx = camada_enlace_receptora(tx + [0] * padding, config)
                                    self.assertFalse(rx.houve_descarte)
                                    self.assertEqual(bytes(bits_para_bytes(rx.payload)), mensagem)

    def test_aceita_string_de_bits(self):
        config = ConfiguracaoEnlace()
        tx = texto(camada_enlace_transmissora("01000001", config))
        self.assertEqual(camada_enlace_receptora(tx, config).payload, bits("01000001"))


class DeteccaoDeErros(unittest.TestCase):
    def test_erro_de_um_bit_no_corpo_e_detectado(self):
        for controle in (TipoControleErro.PARIDADE_PAR, TipoControleErro.CHECKSUM, TipoControleErro.CRC32):
            config = ConfiguracaoEnlace("contagem_caracteres", controle, 16)
            tx = camada_enlace_transmissora(bytes_para_bits(aleatorio(16)), config)
            fim = 8 + 16 * 8 + 1 if controle is TipoControleErro.PARIDADE_PAR else len(tx)
            for posicao in range(8, fim):
                with self.subTest(controle=controle, posicao=posicao):
                    self.assertTrue(camada_enlace_receptora(inverter(tx, posicao), config).houve_descarte)

    def test_crc_detecta_rajadas_de_ate_32_bits(self):
        config = ConfiguracaoEnlace("contagem_caracteres", "crc32", 32)
        tx = camada_enlace_transmissora(bytes_para_bits(aleatorio(32)), config)
        for inicio in range(8, len(tx) - 32, 5):
            for tamanho in (2, 17, 32):
                with self.subTest(inicio=inicio, tamanho=tamanho):
                    erro = inverter(tx, inicio, inicio + tamanho - 1)
                    self.assertTrue(camada_enlace_receptora(erro, config).houve_descarte)

    def test_entrelacamento_detecta_rajadas_de_ate_8_bits(self):
        config = ConfiguracaoEnlace("entrelacamento_bits", "nenhum", 16)
        tx = camada_enlace_transmissora(bytes_para_bits(aleatorio(16)), config)
        for inicio in range(8, len(tx) - 8):
            for tamanho in range(1, 9):
                with self.subTest(inicio=inicio, tamanho=tamanho):
                    erro = inverter(tx, *range(inicio, inicio + tamanho))
                    self.assertTrue(camada_enlace_receptora(erro, config).houve_descarte)


class CorrecaoDeErros(unittest.TestCase):
    def test_hamming_corrige_qualquer_erro_simples_no_corpo(self):
        for enquadramento in ("contagem_caracteres", "entrelacamento_bits"):
            config = ConfiguracaoEnlace(enquadramento, "hamming", 32)
            mensagem = aleatorio(32)
            tx = camada_enlace_transmissora(bytes_para_bits(mensagem), config)
            for posicao in range(8, len(tx)):
                with self.subTest(enquadramento=enquadramento, posicao=posicao):
                    rx = camada_enlace_receptora(inverter(tx, posicao) + [0] * 5, config)
                    self.assertEqual(bytes(bits_para_bytes(rx.payload)), mensagem)


class Validacoes(unittest.TestCase):
    def test_payload_fora_de_bytes_e_rejeitado(self):
        with self.assertRaises(ValueError):
            camada_enlace_transmissora([1, 0, 1], ConfiguracaoEnlace())

    def test_quadro_maior_que_a_contagem_suporta_e_rejeitado(self):
        with self.assertRaises(ValueError):
            camada_enlace_transmissora(bytes_para_bits(aleatorio(300)),
                                       ConfiguracaoEnlace("contagem_caracteres", "hamming", 200))

    def test_configuracoes_invalidas(self):
        for invalida in (dict(tamanho_checksum=12), dict(tamanho_max_quadro=0), dict(enquadramento="x")):
            with self.subTest(**invalida), self.assertRaises(ValueError):
                ConfiguracaoEnlace(**invalida)


if __name__ == "__main__":
    unittest.main()
