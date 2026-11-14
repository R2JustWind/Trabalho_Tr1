"""CamadaFisica.py

Transmissor: bits -> codificação em banda base (NRZ-Polar, Manchester, Bipolar)
                  -> modulação por portadora (ASK, FSK, 8PSK, 32-QAM) -> amostras em volts.
Receptor:            amostras que saíram do canal -> demodulação / decodificação -> bits.

Um sinal é um array do NumPy: cada bit (ou símbolo) ocupa N amostras seguidas,
tomadas a cada 1/fs segundos. Os valores das amostras estão em volts.
A camada de enlace e a interface só precisam chamar fisica_tx e fisica_rx.
"""

import numpy as np


# PARÂMETROS

N = 40  # amostras por bit (banda base, ASK, FSK) ou por símbolo (8PSK, 32-QAM)
assert N % 2 == 0, "N deve ser par: o Manchester divide cada bit em duas metades."

CONFIG_PADRAO = {
    "banda_base": "nrz_polar",       # "nrz_polar", "manchester" ou "bipolar"
    "modulacao": "ask",              # "ask", "fsk", "8psk", "qam32" ou None (transmite só a banda base)
    "taxa_amostragem": 40_000,       # fs, em Hz
    "frequencia_portadora": 1_000,   # fc, em Hz (o FSK usa fc para o bit 0 e 2*fc para o bit 1)
    "amplitude": 1.0,                # V: nível da banda base e amplitude da portadora
}

BANDAS_BASE = ("nrz_polar", "manchester", "bipolar")
MODULACOES = (None, "ask", "fsk", "8psk", "qam32")

# Quantos bits cada técnica coloca em um símbolo (define o padding)
BITS_POR_SIMBOLO = {None: 1, "ask": 1, "fsk": 1, "8psk": 3, "qam32": 5}

# 8PSK com código Gray: fases vizinhas diferem em um bit só.
# A posição p (fase p * 45°) carrega o símbolo p ^ (p >> 1); este dicionário faz o caminho inverso.
NUM_FASES_8PSK = 8
POSICAO_DO_SIMBOLO_8PSK = {p ^ (p >> 1): p for p in range(NUM_FASES_8PSK)}

# 32-QAM em cruz: grade 6x6 (níveis -5, -3, -1, 1, 3, 5) sem os quatro cantos. Símbolo -> (I, Q).
TABELA_QAM32 = {0: (-3, -5), 1: (-1, -5), 2: (1, -5), 3: (3, -5),
                4: (-5, -3), 5: (-3, -3), 6: (-1, -3), 7: (1, -3), 8: (3, -3), 9: (5, -3),
                10: (-5, -1), 11: (-3, -1), 12: (-1, -1), 13: (1, -1), 14: (3, -1), 15: (5, -1),
                16: (-5, 1), 17: (-3, 1), 18: (-1, 1), 19: (1, 1), 20: (3, 1), 21: (5, 1),
                22: (-5, 3), 23: (-3, 3), 24: (-1, 3), 25: (1, 3), 26: (3, 3), 27: (5, 3),
                28: (-3, 5), 29: (-1, 5), 30: (1, 5), 31: (3, 5)}
CONSTELACAO_QAM32 = np.array([TABELA_QAM32[s] for s in range(32)], dtype=float)   # linha s = (I, Q) do símbolo s
ENERGIA_MEDIA_QAM32 = float(np.mean(np.sum(CONSTELACAO_QAM32 ** 2, axis=1)))


# FUNÇÕES AUXILIARES

def validar_config(config):
    """Confere se a configuração é válida. Levanta ValueError com a explicação se não for."""
    for chave in CONFIG_PADRAO:
        if chave not in config:
            raise ValueError(f"Falta a chave '{chave}' na configuração.")
    if config["banda_base"] not in BANDAS_BASE:
        raise ValueError(f"Codificação de banda base desconhecida: {config['banda_base']}")
    if config["modulacao"] not in MODULACOES:
        raise ValueError(f"Modulação desconhecida: {config['modulacao']}")
    if config["amplitude"] <= 0:
        raise ValueError("A amplitude deve ser maior que zero.")

    fs = config["taxa_amostragem"]
    fc = config["frequencia_portadora"]
    if fs <= 0 or fc <= 0:
        raise ValueError("A taxa de amostragem e a frequência da portadora devem ser positivas.")
    # Cada símbolo precisa conter um número inteiro de ciclos da portadora;
    # senão o seno e o cosseno de referência se misturam na demodulação.
    ciclos_por_simbolo = fc * N / fs
    if not np.isclose(ciclos_por_simbolo, round(ciclos_por_simbolo)):
        raise ValueError(f"fc deve ser múltiplo de fs/N = {fs / N:g} Hz "
                         f"(hoje há {ciclos_por_simbolo:g} ciclos por símbolo).")
    # Nyquist: a maior frequência usada (2*fc, no bit 1 do FSK) deve ficar abaixo de fs/2.
    if 2 * fc >= fs / 2:
        raise ValueError(f"2*fc = {2 * fc:g} Hz precisa ficar abaixo de fs/2 = {fs / 2:g} Hz.")

def validar_bits(bits):
    """Confere se a entrada é uma sequência de 0 e 1 e devolve uma lista de int (cópia)."""
    if any(b not in (0, 1) for b in bits):
        raise ValueError("Os bits devem ser os inteiros 0 ou 1.")
    return [int(b) for b in bits]

def completar_bits(bits, k):
    """Padding: acrescenta zeros no fim até o número de bits ser múltiplo de k."""
    faltam = (-len(bits)) % k
    return list(bits) + [0] * faltam

def dividir_em_blocos(sinal):
    """Confere o tamanho do sinal e devolve uma matriz com uma linha (N amostras) por bit ou símbolo."""
    sinal = np.asarray(sinal, dtype=float)
    if len(sinal) % N != 0:
        raise ValueError(f"O sinal deve ter um múltiplo de {N} amostras (recebeu {len(sinal)}).")
    return sinal.reshape(-1, N)

def bits_para_simbolos(bits, k):
    """Agrupa os bits de k em k e lê cada grupo como número binário: [1, 0, 1] -> 5."""
    pesos = 2 ** np.arange(k - 1, -1, -1)                 # [4, 2, 1] para k = 3
    return np.array(bits, dtype=int).reshape(-1, k) @ pesos

def simbolos_para_bits(simbolos, k):
    """Caminho inverso: cada símbolo vira k bits, do mais para o menos significativo. 5 -> [1, 0, 1]."""
    return [(int(s) >> i) & 1 for s in simbolos for i in range(k - 1, -1, -1)]

def eixo_tempo(num_amostras, taxa_amostragem):
    """Instantes de cada amostra, em segundos: 0, 1/fs, 2/fs, ..."""
    return np.arange(num_amostras) / taxa_amostragem

def referencias(frequencia, taxa_amostragem):
    """Seno e cosseno de referência com a duração de um bit/símbolo (N amostras)."""
    angulo = 2 * np.pi * frequencia * eixo_tempo(N, taxa_amostragem)
    return np.sin(angulo), np.cos(angulo)

def correlacionar(blocos, referencia):
    """Média do produto de cada bloco pela referência. Mede 'quanto' da referência há em cada bloco."""
    return (blocos * referencia).mean(axis=1)


# CODIFICAÇÃO EM BANDA BASE

def codificar_nrz_polar(bits, V):
    """Bit 1 -> +V e bit 0 -> -V durante o bit inteiro."""
    niveis = np.where(np.array(bits) == 1, V, -V)
    return np.repeat(niveis, N).astype(float)

def decodificar_nrz_polar(sinal):
    """Média do bit acima de 0 V -> 1; abaixo -> 0."""
    return (dividir_em_blocos(sinal).mean(axis=1) > 0).astype(int).tolist()

def codificar_manchester(bits, V):
    """Bit 1 -> [-V, +V] (subida no meio do bit); bit 0 -> [+V, -V] (descida)."""
    metades = np.where(np.array(bits)[:, None] == 1, [-V, V], [V, -V])   # uma linha [1ª metade, 2ª metade] por bit
    return np.repeat(metades, N // 2, axis=1).flatten().astype(float)

def decodificar_manchester(sinal):
    """Primeira metade mais baixa que a segunda -> 1 (subida); senão -> 0."""
    blocos = dividir_em_blocos(sinal)
    primeira_metade = blocos[:, :N // 2].mean(axis=1)
    segunda_metade = blocos[:, N // 2:].mean(axis=1)
    return (primeira_metade < segunda_metade).astype(int).tolist()

def codificar_bipolar(bits, V):
    """Bit 0 -> 0 V; bits 1 alternam entre +V e -V."""
    niveis = np.zeros(len(bits))
    proximo_nivel = V
    for i, bit in enumerate(bits):
        if bit == 1:
            niveis[i] = proximo_nivel
            proximo_nivel = -proximo_nivel
    return np.repeat(niveis, N)

def decodificar_bipolar(sinal, V):
    """Média do bit longe de 0 V (|média| > V/2) -> 1; perto de 0 V -> 0."""
    return (np.abs(dividir_em_blocos(sinal).mean(axis=1)) > V / 2).astype(int).tolist()


# MODULAÇÃO POR PORTADORA

def modular_ask(bits, fc, fs, A):
    """Bit 1 -> portadora com amplitude A; bit 0 -> amplitude 0."""
    amplitudes = np.repeat(np.where(np.array(bits) == 1, A, 0.0), N)
    return amplitudes * np.sin(2 * np.pi * fc * eixo_tempo(len(amplitudes), fs))

def demodular_ask(sinal, fc, fs, A):
    """Estima a amplitude de cada bit e compara com o limiar A/2 (meio entre 0 e A)."""
    seno, _ = referencias(fc, fs)
    # A*sen(wt) vezes sen(wt) tem média A/2; o fator 2 devolve a amplitude A.
    amplitudes_estimadas = 2 * correlacionar(dividir_em_blocos(sinal), seno)
    return (amplitudes_estimadas >= A / 2).astype(int).tolist()

def modular_fsk(bits, f0, f1, fs, A):
    """Bit 0 -> frequência f0; bit 1 -> f1, com fase contínua entre os bits."""
    frequencias = np.repeat(np.where(np.array(bits) == 1, f1, f0), N)
    # Soma acumulada = fase acumulada: cada bit começa onde o anterior terminou (sem saltos no sinal).
    # Subtrair a frequência da própria amostra faz a fase começar em 0, como nas outras modulações.
    fase = 2 * np.pi * (np.cumsum(frequencias) - frequencias) / fs
    return A * np.sin(fase)

def demodular_fsk(sinal, f0, f1, fs):
    """Compara a energia de cada bit em f0 e em f1. A maior decide o bit."""
    blocos = dividir_em_blocos(sinal)

    def energia(frequencia):
        seno, cosseno = referencias(frequencia, fs)
        return correlacionar(blocos, seno) ** 2 + correlacionar(blocos, cosseno) ** 2

    return (energia(f1) > energia(f0)).astype(int).tolist()

def modular_8psk(bits, fc, fs, A):
    """Cada 3 bits escolhem uma de 8 fases (múltiplos de 45°), com código Gray."""
    simbolos = bits_para_simbolos(bits, 3)
    posicoes = np.array([POSICAO_DO_SIMBOLO_8PSK[int(s)] for s in simbolos], dtype=int)
    fases = np.repeat(posicoes * (2 * np.pi / NUM_FASES_8PSK), N)
    return A * np.sin(2 * np.pi * fc * eixo_tempo(len(fases), fs) + fases)

def demodular_8psk(sinal, fc, fs):
    """Mede a fase de cada símbolo e escolhe a mais próxima entre as 8 possíveis."""
    blocos = dividir_em_blocos(sinal)
    seno, cosseno = referencias(fc, fs)
    # A*sen(wt + fase) = A*sen(wt)*cos(fase) + A*cos(wt)*sen(fase), então:
    componente_cos = 2 * correlacionar(blocos, seno)      # vale A*cos(fase)
    componente_sen = 2 * correlacionar(blocos, cosseno)   # vale A*sen(fase)
    fase = np.arctan2(componente_sen, componente_cos) % (2 * np.pi)
    posicoes = np.round(fase / (2 * np.pi / NUM_FASES_8PSK)).astype(int) % NUM_FASES_8PSK
    simbolos = posicoes ^ (posicoes >> 1)                 # desfaz o código Gray
    return simbolos_para_bits(simbolos, 3)

def modular_qam32(bits, fc, fs, A):
    """Cada 5 bits escolhem um ponto (I, Q) da constelação: sinal = I*cos(wt) - Q*sen(wt)."""
    escala = A / np.sqrt(ENERGIA_MEDIA_QAM32)             # normaliza a potência média para A²/2
    pontos = CONSTELACAO_QAM32[bits_para_simbolos(bits, 5)] * escala
    I = np.repeat(pontos[:, 0], N)
    Q = np.repeat(pontos[:, 1], N)
    angulo = 2 * np.pi * fc * eixo_tempo(len(I), fs)
    return I * np.cos(angulo) - Q * np.sin(angulo)

def demodular_qam32(sinal, fc, fs, A):
    """Mede (I, Q) de cada símbolo e escolhe o ponto da constelação mais próximo."""
    escala = A / np.sqrt(ENERGIA_MEDIA_QAM32)
    blocos = dividir_em_blocos(sinal)
    seno, cosseno = referencias(fc, fs)
    I = 2 * correlacionar(blocos, cosseno) / escala
    Q = -2 * correlacionar(blocos, seno) / escala
    # Matriz de distâncias²: linha = símbolo recebido, coluna = ponto da constelação.
    distancias = (I[:, None] - CONSTELACAO_QAM32[:, 0]) ** 2 + (Q[:, None] - CONSTELACAO_QAM32[:, 1]) ** 2
    simbolos = distancias.argmin(axis=1)                  # coluna mais próxima de cada linha
    return simbolos_para_bits(simbolos, 5)


# ESCOLHA DA TÉCNICA A PARTIR DA CONFIGURAÇÃO

def codificar_banda_base(bits, config):
    """Aplica a codificação de banda base escolhida na configuração."""
    tecnica, V = config["banda_base"], config["amplitude"]
    if tecnica == "nrz_polar":
        return codificar_nrz_polar(bits, V)
    if tecnica == "manchester":
        return codificar_manchester(bits, V)
    return codificar_bipolar(bits, V)

def decodificar_banda_base(sinal, config):
    """Aplica a decodificação de banda base escolhida na configuração."""
    tecnica, V = config["banda_base"], config["amplitude"]
    if tecnica == "nrz_polar":
        return decodificar_nrz_polar(sinal)
    if tecnica == "manchester":
        return decodificar_manchester(sinal)
    return decodificar_bipolar(sinal, V)

def modular(bits, config):
    """Aplica a modulação por portadora escolhida na configuração."""
    tecnica = config["modulacao"]
    fs, fc, A = config["taxa_amostragem"], config["frequencia_portadora"], config["amplitude"]
    if tecnica == "ask":
        return modular_ask(bits, fc, fs, A)
    if tecnica == "fsk":
        return modular_fsk(bits, fc, 2 * fc, fs, A)
    if tecnica == "8psk":
        return modular_8psk(bits, fc, fs, A)
    return modular_qam32(bits, fc, fs, A)

def demodular(sinal, config):
    """Aplica a demodulação escolhida na configuração."""
    tecnica = config["modulacao"]
    fs, fc, A = config["taxa_amostragem"], config["frequencia_portadora"], config["amplitude"]
    if tecnica == "ask":
        return demodular_ask(sinal, fc, fs, A)
    if tecnica == "fsk":
        return demodular_fsk(sinal, fc, 2 * fc, fs)       # compara energias: não depende de A
    if tecnica == "8psk":
        return demodular_8psk(sinal, fc, fs)              # só mede ângulos: não depende de A
    return demodular_qam32(sinal, fc, fs, A)


# TRANSMISSOR E RECEPTOR (o que o Simulador chama)

def fisica_tx(bits, config=None):
    """Recebe os bits do enlace e devolve o que vai para o canal.

    Retorna um dicionário:
      "sinal"            -> amostras em volts que vão para o canal (é isso que o ruído AWGN altera)
      "tempo"            -> instante de cada amostra de "sinal", em segundos (eixo x do gráfico)
      "sinal_banda_base" -> saída do codificador de banda base (amostrador de sinal do TX)
      "tempo_banda_base" -> eixo do tempo de "sinal_banda_base"
      "bits_enviados"    -> bits realmente transmitidos (incluindo os zeros de padding)
    """
    config = CONFIG_PADRAO if config is None else config
    validar_config(config)
    bits = validar_bits(bits)
    fs = config["taxa_amostragem"]

    # Padding primeiro: assim a banda base do TX e a do RX mostram os mesmos bits nos gráficos.
    bits_enviados = completar_bits(bits, BITS_POR_SIMBOLO[config["modulacao"]])
    sinal_banda_base = codificar_banda_base(bits_enviados, config)

    if config["modulacao"] is None:
        sinal = sinal_banda_base
    else:
        sinal = modular(bits_enviados, config)

    return {
        "sinal": sinal,
        "tempo": eixo_tempo(len(sinal), fs),
        "sinal_banda_base": sinal_banda_base,
        "tempo_banda_base": eixo_tempo(len(sinal_banda_base), fs),
        "bits_enviados": bits_enviados,
    }

def fisica_rx(sinal, config=None):
    """Recebe as amostras que saíram do canal e devolve os bits para o enlace.

    O receptor não sabe quantos zeros de padding o transmissor colocou: devolve todos os bits
    decodificados, e o desenquadramento do enlace ignora o que vier depois do fim do quadro.

    Retorna um dicionário:
      "bits"             -> bits recuperados (lista de int), entregues ao enlace
      "sinal_banda_base" -> banda base no receptor (amostrador de sinal do RX): o próprio sinal
                            recebido se não há portadora, ou a banda base refeita a partir dos bits
      "tempo_banda_base" -> eixo do tempo de "sinal_banda_base"
    """
    config = CONFIG_PADRAO if config is None else config
    validar_config(config)
    sinal = np.asarray(sinal, dtype=float)
    fs = config["taxa_amostragem"]

    if config["modulacao"] is None:
        bits = decodificar_banda_base(sinal, config)
        sinal_banda_base = sinal
    else:
        bits = demodular(sinal, config)
        sinal_banda_base = codificar_banda_base(bits, config)

    return {
        "bits": bits,
        "sinal_banda_base": sinal_banda_base,
        "tempo_banda_base": eixo_tempo(len(sinal_banda_base), fs),
    }