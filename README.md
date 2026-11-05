# Automação do setup experimental para o estudo de arritmias cardíacas em modelos animais

Sistema modular, de baixo custo, para **monitoramento e controle automatizado** das variáveis críticas do sistema de Langendorff do Laboratório de Eletrofisiologia Cardíaca (**HEartLab**) da Universidade Federal do ABC: temperatura, pressão de perfusão, vazão e fornecimento de gás carbogênico.

Projeto de Iniciação Científica financiado pela **FAPESP** (processo nº 2025/22698-7).

## Arquitetura

| Módulo | Placa | Função |
|---|---|---|
| Aquisição de Dados dos Sensores | Arduino Nano + nRF24L01 | Lê pressão (Honeywell ABPDANN005PG2A3), vazão e temperatura de perfusão (Sensirion SLF3S-4000B) e temperatura do tanque (termopar tipo K + MAX6675) |
| Central de Comunicação | ESP32-WROOM-32 + nRF24L01 | Recebe os pacotes a cada 200 ms, emite alarmes (LEDs e buzzer), calcula o PID de vazão, decide o acionamento dos relés e conversa com o computador por USB ou Bluetooth |
| Controle | Arduino Nano + nRF24L01 | Executa os comandos: relés (banho-maria e bomba de água quente), servo MG90S da válvula de solução, servos MG995 das válvulas de gás e leitura do encoder AS5600 |

Os módulos se comunicam sem fio em 2,4 GHz. A interface gráfica em Python mostra as variáveis em tempo real e grava os dados em CSV.

## Estrutura do repositório

```
automacao-langendorff-heartlab/
├── firmware/      códigos dos três módulos (Arduino IDE)       → Apêndice B do relatório
├── hardware/      peças modeladas em 3D e impressas em PLA      → Apêndice C do relatório
└── software/      interface gráfica (Python: Tkinter, Matplotlib, PySerial) → Apêndice D do relatório
```

Cada pasta tem um `README.md` com instruções.

## Faixas fisiológicas de referência

Os limites exatos de alarme e de controle usados no firmware estão em `firmware/README.md`.

| Variável | Faixa |
|---|---|
| Temperatura de perfusão | 37 a 39 °C |
| Pressão de perfusão | 40 a 60 mmHg |
| Vazão de perfusão | 20 a 40 ml/min |
| pH da solução (via gás carbogênico) | 7,4 ± 0,05 |

## Autores

- Murilo Leal Santos – bolsista de Iniciação Científica (UFABC)
- João Loures Salinet Júnior – orientador (Engenharia Biomédica, CECS-UFABC)

## Publicação relacionada

SANTOS, M. L.; SILVA, V.; SALINET, J. *Automation of the experimental setup for functional studies in isolated perfused hearts.* XXX Congresso Brasileiro de Engenharia Biomédica (CBEB 2026), Fortaleza, 2026.

## Agradecimentos

Este trabalho foi realizado com apoio da Fundação de Amparo à Pesquisa do Estado de São Paulo (FAPESP), processo nº 2025/22698-7. As opiniões, hipóteses e conclusões ou recomendações expressas neste material são de responsabilidade do autor e não necessariamente refletem a visão da FAPESP.

## Licença

A definir com o orientador.
