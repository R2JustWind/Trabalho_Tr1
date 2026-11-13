# Trabalho_Tr1

Aplicação de chat do trabalho final de TR1, com GUI Linux GTK e separação entre
interface/aplicação e camada de enlace.

## Organização

- `interface/`: GUI GTK, aplicação de chat, conversão texto↔bytes, controlador
  e adaptador contratual.
- `enlace/`: implementação da camada de enlace do simulador.
- `tests/`: testes da interface, aplicação e contratos mockados.

## Estado atual

Esta base implementa a aplicação, a GUI e o adaptador para a camada de enlace.
As camadas física, canal e a rotina de transmissão ponta a ponta ainda dependem
da implementação dos demais integrantes. O `DisconnectedLinkAdapter` permanece
disponível para testes isolados; o adaptador de enlace real não declara entrega
sem que física/canal forneçam os dados correspondentes.

Bits e status do enlace são exibidos quando fornecidos pelo adaptador. Amostras,
ruído e resultados das camadas física/canal só serão exibidos após a integração real.

UTF-8 e payload em `bytes` são escolhas provisórias até validação com o grupo.

## Executar testes

```bash
python -m unittest discover -s tests -v
```

## Executar a GUI no Linux

Com Python, GTK3 e PyGObject já instalados no sistema:

```bash
python -m interface.main
```

Nenhuma dependência é instalada pelo projeto.
