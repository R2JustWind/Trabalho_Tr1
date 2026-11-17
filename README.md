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

O caminho padrão de `Simulador` usa as funções completas de
`fisica/CamadaFisica.py`. A interface injeta a configuração física selecionada
e coleta as amostras reais de TX/RX. O arquivo `simulador/fisica_provisoria.py`
permanece somente como adaptador simples para testes explícitos de concorrência
e não é usado como caminho de produção.

## Técnicas implementadas

| Camada | Técnicas |
|---|---|
| **Enlace — enquadramento** | Contagem de caracteres · Entrelaçamento de bits · Byte stuffing · Bit stuffing |
| **Enlace — detecção de erros** | Bit de paridade par · Checksum · CRC-32 (IEEE 802) |
| **Enlace — correção de erros** | Código de Hamming |
| **Física — banda base** | NRZ-Polar · Manchester · Bipolar |
| **Física — portadora** | Sem portadora · ASK · FSK · 8PSK · 32-QAM |
| **Meio de comunicação** | Ruído AWGN com média e desvio padrão configuráveis |

Os protocolos de comunicação são implementados do zero. NumPy e Matplotlib são usados apenas como apoio para processamento numérico e visualização, não para executar os protocolos.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `InterfaceGUI.py` | Interface gráfica GTK, aplicação de chat e adaptadores |
| `fisica/` | Camada física: Codificação e Decodificação em banda base, Modulação e Demodulação por portadora |
| `enlace/` | Camada de enlace: enquadramento, detecção e correção de erros |
| `simulador/` | Rotina principal com as threads TX e RX e o meio de comunicação |
| `tests/` | Testes de todas as partes |

## Como executar

O projeto roda no Linux. No Windows, use o WSL (no Windows 11 ele já abre janelas gráficas).

### Pré-requisitos obrigatórios

Para abrir a interface gráfica, o ambiente precisa ter **GTK 3**, **PyGObject**,
**PyCairo** e o backend GTK3 do Matplotlib. GTK/PyGObject/PyCairo são
dependências do sistema operacional; o `requirements.txt` instala apenas as
dependências Python do projeto.

#### Ubuntu ou WSL2 com WSLg

Instale as bibliotecas do sistema. O pacote `python3-gi-cairo` é importante:
ele conecta o Cairo ao PyGObject e evita o erro `GTK-based backends requires
cairo`.

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv \
  python3-gi python3-gi-cairo python3-cairo \
  libcairo2 gir1.2-gtk-3.0 python3-matplotlib
```

O modo recomendado é criar um ambiente virtual que também enxergue os módulos
GTK/Cairo instalados pelo `apt`:

```bash
python3 -m venv --system-site-packages .venv-gtk
source .venv-gtk/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

Não instale `pycairo` com `pip` como primeiro passo. Em algumas versões do
Python ele tenta compilar o pacote e termina com `metadata-generation-failed`;
`python3-cairo` e `python3-gi-cairo` do Ubuntu já fornecem o suporte necessário.

Confirme o backend antes de abrir a janela:

```bash
python -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk; import cairo; from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg; print('GTK3 + Cairo + Matplotlib OK')"
```

Se esse comando funcionar, execute:

```bash
python InterfaceGUI.py
```

Se o ambiente virtual já tiver sido criado sem `--system-site-packages`, crie
outro com o comando acima ou use temporariamente o Python do sistema:

```bash
/usr/bin/python3 InterfaceGUI.py
```

Para diagnosticar qual Python está sendo usado:

```bash
which python3
python3 -c "import sys; print(sys.executable)"
```

No Windows 11, o WSL2 com WSLg normalmente fornece o display gráfico sem
configuração adicional. Em WSL1 ou em WSL2 sem WSLg, é necessário configurar
um servidor X externo; isso é uma dependência do ambiente, não do simulador.

#### Testes sem abrir a GUI

```bash
python -m tests.test_fisica
python -m unittest discover -s tests -v
```

Os testes também rodam automaticamente no GitHub a cada push.
