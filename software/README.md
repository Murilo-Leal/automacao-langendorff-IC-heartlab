# Interface gráfica – ESP32 Hub: Monitor e Controle

Supervisório em **Python** (Tkinter + Matplotlib + PySerial) para o firmware `firmware/modulo_central_esp32`. Mostra as variáveis em tempo real, envia comandos ao sistema e grava os dados em CSV.

## Requisitos

- Python 3.8 ou mais recente
- Bibliotecas em `gui_python/requirements.txt`: `pyserial`, `matplotlib` e `numpy`
- O Tkinter já vem com o Python no Windows e no macOS. No Linux, instale `python3-tk`.

## Como executar

```bash
cd software/gui_python
pip install -r requirements.txt
python monitor_esp32.py
```

1. Conecte o Módulo Central (ESP32) na USB do computador.
2. Escolha a porta (ex.: `COM3` no Windows, `/dev/ttyUSB0` no Linux), mantenha **115200 baud** e clique em **Conectar**.
3. Para testar sem o hardware, escolha **SIMULADOR** na lista de portas. Ele imita o firmware, incluindo o PID, os relés e os alarmes.

## Funções da interface

| Área | O que faz |
|---|---|
| **Leituras** | Cartões de vazão, temperatura de perfusão, pressão e temperatura do tanque para o NODE 2 e o NODE 4, em verde (dentro da faixa) ou vermelho (fora) |
| **Alarmes** | Estado de alerta de cada nó e contador de falhas de comunicação com o NODE 3 |
| **Processo** | Setpoint de vazão (`SET_FLUXO`), PID automático/manual, relé 1 (tanque), relé 2 (fluxo) e abertura do servo 1 |
| **Oxigenação** | Abertura (0–100 %) dos servos 2, 3 e 4 das válvulas de gás, individualmente ou todos juntos |
| **Gráficos** | Séries temporais das quatro variáveis, com os limites de alarme e a abertura dos servos; janela de 30 s a 30 min |
| **Monitor serial** | Mensagens do ESP32 coloridas por tipo, campo para comando livre ao NODE 3 e botão para salvar o log |
| **Gravar CSV** | Começa e para a gravação dos dados num arquivo escolhido pelo usuário |
| **Reiniciar ESP** | Reinicia o ESP32 por um pulso na linha RTS |

Os limites usados para colorir os cartões são os mesmos do firmware: temperatura de perfusão 37–41 °C, temperatura do tanque 22–41 °C, pressão até 80 mmHg e vazão em setpoint ± 5 ml/min. O firmware só avalia o NODE 2; o NODE 4 é avaliado pela própria interface.

A faixa de ângulo de cada servo (0 % = ângulo mínimo, 100 % = máximo) fica no dicionário `SERVOS`, no início do arquivo. Ajuste-a conforme a mecânica de cada válvula.

## Formato do CSV

O arquivo usa **`;` como separador** e grava uma linha por pacote de sensores recebido (a cada ~200 ms por nó). O nome padrão é `dados_esp32_AAAAMMDD_HHMMSS.csv`.

| Coluna | Conteúdo | Unidade |
|---|---|---|
| `timestamp` | Data e hora do computador (ISO 8601, com milissegundos) | – |
| `node` | Nó de origem (2 ou 4) | – |
| `fluxo` | Vazão de perfusão | ml/min |
| `temp_fluxo` | Temperatura de perfusão (sensor de fluxo) | °C |
| `pressao` | Pressão de perfusão | mmHg |
| `temp_tanque` | Temperatura do tanque de imersão (MAX6675) | °C |
| `setpoint` | Setpoint de vazão vigente | ml/min |
| `servo1_pct` … `servo4_pct` | Última abertura confirmada de cada servo (vazio se desconhecida) | % |
| `pid` | Controle PID ligado (1) ou desligado (0) | – |
| `rele1` | Relé 1 – banho-maria do tanque (1 = ligado) | – |
| `rele2` | Relé 2 – bomba de água quente (1 = ligado) | – |
| `alerta` | Alguma variável do nó fora da faixa (1) | – |

Um exemplo de arquivo pode ser colocado em `dados_exemplo/`.
