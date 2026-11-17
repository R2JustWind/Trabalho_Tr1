"""Regressoes para falhas encontradas na auditoria do professor."""

import time
import unittest

from InterfaceGUI import (
    ChatController,
    EnlaceLinkAdapter,
    SimulationConfig,
    TransmissionState,
)
from enlace.CamadaEnlace import (
    ConfiguracaoEnlace,
    TipoControleErro,
    TipoEnquadramento,
    camada_enlace_receptora,
    camada_enlace_transmissora,
)
from enlace.bits import bytes_para_bits
from simulador.Simulador import ConfiguracaoSimulacao, Simulador
from simulador.canal import MeioComunicacao


class RegressaoEnlace(unittest.TestCase):
    def test_fluxo_sem_quadro_e_rejeitado(self):
        for enquadramento in TipoEnquadramento:
            for controle in TipoControleErro:
                with self.subTest(enquadramento=enquadramento, controle=controle):
                    resultado = camada_enlace_receptora(
                        [], ConfiguracaoEnlace(enquadramento, controle)
                    )
                    self.assertTrue(resultado.houve_descarte)

    def test_payload_vazio_serializado_tem_quadro_valido(self):
        for enquadramento in TipoEnquadramento:
            for controle in TipoControleErro:
                with self.subTest(enquadramento=enquadramento, controle=controle):
                    config = ConfiguracaoEnlace(enquadramento, controle)
                    fluxo = camada_enlace_transmissora([], config)
                    resultado = camada_enlace_receptora(fluxo, config)
                    self.assertFalse(resultado.houve_descarte)
                    self.assertEqual(resultado.payload, [])

    def test_adaptador_nao_entrega_fluxo_vazio(self):
        eventos = []
        payload = EnlaceLinkAdapter().receive_bits(
            [], "sem-quadro", SimulationConfig(), eventos.append
        )
        self.assertEqual(payload.validation_status.value, "rejected")
        self.assertEqual(eventos[-1].state, TransmissionState.REJECTED)

    def test_quadro_truncado_e_rejeitado(self):
        for enquadramento in TipoEnquadramento:
            config = ConfiguracaoEnlace(enquadramento, TipoControleErro.CRC32)
            fluxo = camada_enlace_transmissora(bytes_para_bits(b"abc"), config)
            with self.subTest(enquadramento=enquadramento):
                self.assertTrue(camada_enlace_receptora(fluxo[:-1], config).houve_descarte)


class RegressaoCanalESimulador(unittest.TestCase):
    def test_canal_rejeita_parametros_nao_finitos(self):
        for kwargs in (
            {"media": float("nan")},
            {"media": float("inf")},
            {"desvio_padrao": float("nan")},
            {"desvio_padrao": float("inf")},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                MeioComunicacao(**kwargs)

    def test_simulador_padrao_usa_fisica_real(self):
        resultado = Simulador(
            ConfiguracaoSimulacao(
                ConfiguracaoEnlace(
                    TipoEnquadramento.CONTAGEM_CARACTERES,
                    TipoControleErro.CRC32,
                )
            )
        ).enviar("fisica real")
        self.assertEqual(resultado.texto_recebido, "fisica real")
        self.assertGreater(len(resultado.sinal_tx), 0)
        self.assertNotEqual(set(resultado.sinal_tx), {1.0, -1.0})

    def test_timeout_e_convertido_em_erro_controlado(self):
        def transmissora(bits):
            time.sleep(0.1)
            return [float(bit) for bit in bits]

        def receptora(sinal):
            return [int(round(amostra)) for amostra in sinal]

        with self.assertRaisesRegex(TimeoutError, "tempo limite"):
            Simulador(
                ConfiguracaoSimulacao(tempo_limite=0.01),
                fisica_transmissora=transmissora,
                fisica_receptora=receptora,
            ).enviar("timeout")


class RegressaoAplicacao(unittest.TestCase):
    def test_falha_de_configuracao_no_adapter_nao_vaza_para_a_gui(self):
        class Adapter:
            def submit(self, payload, on_event):
                raise ValueError("configuracao invalida")

        eventos = []
        ChatController(Adapter()).send("mensagem", SimulationConfig(), eventos.append)
        self.assertEqual(eventos[-1].state, TransmissionState.FAILED)


if __name__ == "__main__":
    unittest.main()
