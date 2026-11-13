import threading
import unittest

from enlace.CamadaEnlace import ConfiguracaoEnlace, SituacaoQuadro, TipoControleErro, TipoEnquadramento
from simulador import fisica_provisoria
from simulador.canal import MeioComunicacao
from simulador.Simulador import ConfiguracaoSimulacao, Simulador

MENSAGEM = "Olá, TR1! Teste do simulador com mais de um quadro."


def simular(enquadramento="contagem_caracteres", controle="crc32", desvio=0.0, semente=1, mensagem=MENSAGEM, **fisica):
    config = ConfiguracaoSimulacao(ConfiguracaoEnlace(enquadramento, controle, 16), desvio_ruido=desvio, semente_ruido=semente)
    return Simulador(config, **fisica).enviar(mensagem)


class MeioDeComunicacao(unittest.TestCase):
    def test_sem_ruido_o_sinal_nao_muda(self):
        self.assertEqual(MeioComunicacao().aplicar_ruido([1.0, -1.0]), [1.0, -1.0])

    def test_media_e_desvio_do_ruido(self):
        ruido = MeioComunicacao(media=0.5, desvio_padrao=2.0, semente=3).aplicar_ruido([0.0] * 20000)
        media = sum(ruido) / len(ruido)
        desvio = (sum((r - media) ** 2 for r in ruido) / len(ruido)) ** 0.5
        self.assertAlmostEqual(media, 0.5, delta=0.05)
        self.assertAlmostEqual(desvio, 2.0, delta=0.05)

    def test_desvio_negativo_e_rejeitado(self):
        with self.assertRaises(ValueError):
            MeioComunicacao(desvio_padrao=-1)


class SimulacaoPontaAPonta(unittest.TestCase):
    def test_todas_as_combinacoes_sem_ruido(self):
        for enquadramento in TipoEnquadramento:
            for controle in TipoControleErro:
                with self.subTest(enquadramento=enquadramento, controle=controle):
                    resultado = simular(enquadramento, controle)
                    self.assertEqual(resultado.texto_recebido, MENSAGEM)
                    self.assertFalse(resultado.recepcao_enlace.houve_descarte)

    def test_sinal_transmitido_em_volts(self):
        resultado = simular()
        self.assertEqual(set(resultado.sinal_tx), {fisica_provisoria.TENSAO, -fisica_provisoria.TENSAO})
        self.assertEqual(len(resultado.sinal_tx) % fisica_provisoria.AMOSTRAS_POR_BIT, 0)

    def test_padding_da_fisica_chega_ao_enlace(self):
        com_padding = 0
        for tamanho in range(1, 10):
            mensagem = "a" * tamanho
            resultado = simular("bit_stuffing", "paridade_par", mensagem=mensagem)
            com_padding += len(resultado.bits_fisica_rx) > len(resultado.bits_enlace_tx)
            self.assertEqual(resultado.texto_recebido, mensagem)
        self.assertGreater(com_padding, 0)

    def test_ruido_baixo_nao_altera_a_mensagem(self):
        for semente in range(5):
            self.assertEqual(simular(desvio=0.3, semente=semente).texto_recebido, MENSAGEM)

    def test_crc_descarta_quadros_com_ruido_alto(self):
        for semente in range(10):
            resultado = simular(desvio=2.0, semente=semente)
            if resultado.texto_recebido != MENSAGEM:
                self.assertTrue(resultado.recepcao_enlace.houve_descarte)

    def test_hamming_corrige_erros_vindos_do_canal(self):
        situacoes = [quadro.situacao for semente in range(10)
                     for quadro in simular("entrelacamento_bits", "hamming", desvio=1.4, semente=semente).recepcao_enlace.quadros]
        self.assertIn(SituacaoQuadro.CORRIGIDO, situacoes)

    def test_transmissor_e_receptor_rodam_em_threads_separadas(self):
        threads = {}

        def transmissora(bits):
            threads["tx"] = threading.current_thread().name
            return fisica_provisoria.camada_fisica_transmissora(bits)

        def receptora(sinal):
            threads["rx"] = threading.current_thread().name
            return fisica_provisoria.camada_fisica_receptora(sinal)

        simular(fisica_transmissora=transmissora, fisica_receptora=receptora)
        self.assertEqual(threads, {"tx": "TX", "rx": "RX"})

    def test_mensagem_vazia_e_rejeitada(self):
        with self.assertRaises(ValueError):
            simular(mensagem="   ")


if __name__ == "__main__":
    unittest.main()
