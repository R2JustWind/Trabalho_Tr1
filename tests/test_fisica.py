"""Testes da camada física. Rode com:  python3 test_fisica.py"""
import numpy as np
from fisica.CamadaFisica import (CONFIG_PADRAO, BANDAS_BASE, MODULACOES, N,
                          fisica_tx, fisica_rx, validar_config)

rng = np.random.default_rng(0)


def configuracao(**mudancas):
    """CONFIG_PADRAO com algumas chaves trocadas."""
    return dict(CONFIG_PADRAO, **mudancas)

def todas_as_configuracoes(**mudancas):
    """Uma configuração para cada combinação de banda base e modulação."""
    for banda_base in BANDAS_BASE:
        for modulacao in MODULACOES:
            yield configuracao(banda_base=banda_base, modulacao=modulacao, **mudancas)

def nome(config):
    return f"{config['banda_base']}/{config['modulacao']}"

def erros_ida_e_volta(bits, config, media=0.0, sigma=0.0):
    """Transmite, soma ruído gaussiano n(media, sigma) e recebe. Devolve quantos bits chegaram errados."""
    tx = fisica_tx(bits, config)
    recebido = tx["sinal"] + rng.normal(media, sigma, len(tx["sinal"]))
    rx = fisica_rx(recebido, config)
    assert len(rx["bits"]) >= len(bits), f"{nome(config)}: devolveu menos bits do que recebeu"
    return sum(a != b for a, b in zip(bits, rx["bits"]))

def deve_falhar(funcao, descricao):
    try:
        funcao()
    except ValueError:
        return
    raise AssertionError(f"deveria ter levantado ValueError: {descricao}")


def teste_sem_ruido():
    for n in (1, 2, 4, 7, 13, 64, 301):      # tamanhos que não são múltiplos de 3 nem de 5
        for config in todas_as_configuracoes():
            bits = rng.integers(0, 2, n).tolist()
            assert erros_ida_e_volta(bits, config) == 0, f"{nome(config)} com {n} bits"
    print("OK  ida e volta sem ruído: 15 combinações x 7 tamanhos")

def teste_casos_extremos():
    for bits in ([0] * 20, [1] * 20, [0, 1] * 10):
        for config in todas_as_configuracoes():
            assert erros_ida_e_volta(bits, config) == 0, f"{nome(config)} com {bits[:4]}..."
    print("OK  só zeros, só uns e alternado")

def teste_mensagem_vazia():
    for config in todas_as_configuracoes():
        tx = fisica_tx([], config)
        assert len(tx["sinal"]) == 0 and fisica_rx(tx["sinal"], config)["bits"] == []
    print("OK  mensagem vazia")

def teste_tipos():
    for config in todas_as_configuracoes():
        rx = fisica_rx(fisica_tx([1, 0, 1, 1, 0, 1, 1], config)["sinal"], config)
        assert all(type(b) is int for b in rx["bits"]), f"{nome(config)} devolveu bits que não são int"
    print("OK  bits devolvidos são int em todas as técnicas")

def teste_nao_altera_entrada():
    bits = [1, 0, 1, 1]
    for config in todas_as_configuracoes():
        fisica_tx(bits, config)
    assert bits == [1, 0, 1, 1]
    print("OK  fisica_tx não altera a lista recebida")

def teste_padding():
    bits = [1, 0, 1, 1, 0, 1, 1]   # 7 bits
    esperado = {None: 7, "ask": 7, "fsk": 7, "8psk": 9, "qam32": 10}
    for modulacao, total in esperado.items():
        enviados = fisica_tx(bits, configuracao(modulacao=modulacao))["bits_enviados"]
        assert len(enviados) == total and enviados[:7] == bits, f"{modulacao}: {enviados}"
    print("OK  padding (8PSK completa para 9 bits, 32-QAM para 10)")

def teste_graficos_consistentes():
    for config in todas_as_configuracoes():
        tx = fisica_tx([1, 0, 1, 1, 0, 1, 1], config)
        rx = fisica_rx(tx["sinal"], config)
        assert len(tx["sinal_banda_base"]) == len(rx["sinal_banda_base"]), f"{nome(config)}: banda base TX ≠ RX"
        assert len(tx["tempo"]) == len(tx["sinal"]), f"{nome(config)}: eixo do tempo com tamanho errado"
    sinal_fsk = fisica_tx([0] * 4, configuracao(modulacao="fsk"))["sinal"]
    esperado = np.sin(2 * np.pi * CONFIG_PADRAO["frequencia_portadora"] * np.arange(4 * N) / CONFIG_PADRAO["taxa_amostragem"])
    assert np.allclose(sinal_fsk, esperado), "FSK com só zeros deveria ser um seno puro de fc começando em 0"
    print("OK  gráficos: banda base do TX e do RX com o mesmo tamanho; FSK começa na fase 0")

def teste_entradas_invalidas():
    deve_falhar(lambda: fisica_tx(list("1011")), "bits em texto")
    deve_falhar(lambda: fisica_tx([1, 2, 0]), "bit com valor 2")
    deve_falhar(lambda: fisica_rx(np.zeros(N + 3)), "sinal com tamanho que não é múltiplo de N")
    deve_falhar(lambda: validar_config(configuracao(modulacao="16qam")), "modulação inexistente")
    deve_falhar(lambda: validar_config(configuracao(banda_base="nrz")), "banda base inexistente")
    deve_falhar(lambda: validar_config(configuracao(amplitude=0)), "amplitude zero")
    deve_falhar(lambda: validar_config(configuracao(frequencia_portadora=1_500)), "ciclos não inteiros")
    deve_falhar(lambda: validar_config(configuracao(frequencia_portadora=10_000)), "acima de Nyquist")
    deve_falhar(lambda: validar_config({"modulacao": "ask"}), "chaves faltando")
    print("OK  entradas e configurações inválidas levantam ValueError")

def teste_outras_portadoras():
    validas = [fc for fc in range(1_000, 10_000, 1_000)]   # múltiplos de fs/N, abaixo de fs/4
    for fc in validas:
        for config in todas_as_configuracoes(frequencia_portadora=fc):
            bits = rng.integers(0, 2, 60).tolist()
            assert erros_ida_e_volta(bits, config) == 0, f"{nome(config)} com fc={fc}"
    print(f"OK  todas as portadoras válidas funcionam: {validas[0]} a {validas[-1]} Hz")

def teste_outras_amplitudes():
    for A in (0.5, 3.3, 5.0, 12.0):
        for config in todas_as_configuracoes(amplitude=A):
            bits = rng.integers(0, 2, 60).tolist()
            assert erros_ida_e_volta(bits, config, sigma=0.05 * A) == 0, f"{nome(config)} com A={A}"
    print("OK  amplitudes 0,5 / 3,3 / 5 / 12 V")


def tabela_potencia():
    print("\nPico e potência média (A = 1 V, potência em 1 Ω):")
    for modulacao in MODULACOES[1:]:
        sinal = fisica_tx(rng.integers(0, 2, 3000).tolist(), configuracao(modulacao=modulacao))["sinal"]
        print(f"  {modulacao:6s} pico {np.abs(sinal).max():.2f} V   potência média {np.mean(sinal ** 2):.2f} W")

def tabela_de_erros(media=0.0):
    sigmas = (0.1, 0.3, 0.5, 0.8, 1.0)
    print(f"\nErros em 3000 bits, ruído com média {media} V (A = 1 V):")
    print(f"{'técnica':>12s} " + " ".join(f"σ={s:<5}" for s in sigmas))
    linhas = [configuracao(banda_base=b, modulacao=None) for b in BANDAS_BASE]
    linhas += [configuracao(modulacao=m) for m in MODULACOES[1:]]
    for config in linhas:
        bits = rng.integers(0, 2, 3000).tolist()
        erros = [erros_ida_e_volta(bits, config, media, s) for s in sigmas]
        print(f"{config['modulacao'] or config['banda_base']:>12s} " + " ".join(f"{e:<7d}" for e in erros))


if __name__ == "__main__":
    teste_sem_ruido()
    teste_casos_extremos()
    teste_mensagem_vazia()
    teste_tipos()
    teste_nao_altera_entrada()
    teste_padding()
    teste_graficos_consistentes()
    teste_entradas_invalidas()
    teste_outras_portadoras()
    teste_outras_amplitudes()
    tabela_potencia()
    tabela_de_erros()
    tabela_de_erros(media=0.8)