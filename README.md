# Simulador de Redes — TR1

[![Testes](https://github.com/R2JustWind/Trabalho_Tr1/actions/workflows/tests.yml/badge.svg)](https://github.com/R2JustWind/Trabalho_Tr1/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![GTK](https://img.shields.io/badge/interface-GTK%203-green)

Trabalho final de **Teleinformática e Redes 1 (UnB)**. Um chat de texto que simula
a comunicação entre um transmissor e um receptor passando pelas camadas de
**aplicação**, **enlace** e **física**, com um meio de comunicação que adiciona
ruído gaussiano ao sinal.

## Como funciona

```
TX:  Aplicação -> Enlace -> Física -> 
Meio de comunicação (ruído)
RX:  Física -> Enlace -> Aplicação
```

O transmissor e o receptor rodam em threads separadas e só se comunicam pelo meio.

## Técnicas implementadas

| Camada | Técnicas |
|---|---|
| **Enlace — enquadramento** | Contagem de caracteres · Entrelaçamento de bits · Byte stuffing · Bit stuffing |
| **Enlace — detecção de erros** | Bit de paridade par · Checksum · CRC-32 (IEEE 802) |
| **Enlace — correção de erros** | Código de Hamming |
| **Física — banda base** | NRZ-Polar · Manchester · Bipolar |
| **Física — portadora** | ASK · FSK · 8PSK · 32-QAM |
| **Meio de comunicação** | Ruído AWGN com média e desvio padrão configuráveis |

Os algoritmos são implementados do zero, sem bibliotecas externas.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `interface/` | Interface gráfica GTK e camada de aplicação |
| `enlace/` | Camada de enlace: enquadramento, detecção e correção de erros |
| `simulador/` | Rotina principal com as threads TX e RX e o meio de comunicação |
| `tests/` | Testes de todas as partes |

## Como executar

O projeto roda no Linux. No Windows, use o WSL (no Windows 11 ele já abre janelas gráficas).

**Instalar as dependências da interface** (Ubuntu/WSL):

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 python3-matplotlib
```

**Abrir a interface:**

```bash
python3 -m interface.main
```

**Rodar os testes:**

```bash
python3 -m unittest discover -s tests -v
```

Os testes também rodam automaticamente no GitHub a cada push.
