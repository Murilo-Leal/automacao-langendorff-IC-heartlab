# Firmware dos módulos

Códigos desenvolvidos na **Arduino IDE**. Cada código fica numa pasta com o **mesmo nome do arquivo `.ino` principal**, como a Arduino IDE exige. Os arquivos `.cpp` e `.h` da mesma pasta são compilados juntos automaticamente.

| Pasta | Placa (Ferramentas → Placa) | Nó do rádio | Versão de origem |
|---|---|---|---|
| `modulo_aquisicao_nano/` | Arduino Nano | Node 2 (transmissor) | `SensorData_Compativel_5` |
| `modulo_central_esp32/` | ESP32 Dev Module (ESP32-WROOM-32) | Central (receptor) | `ESP_Central_Compativel_14_Dinamico` |
| `modulo_controle_nano/` | Arduino Nano | Node 3 (atuador) | `Node3_Atuador_Sensor_4Servos` |

## Como gravar

1. Instale as bibliotecas de `bibliotecas.txt` (Ferramentas → Gerenciar Bibliotecas).
2. Para o ESP32, instale o pacote **esp32 by Espressif Systems** (Ferramentas → Placa → Gerenciador de Placas).
3. Abra o `.ino` do módulo, escolha a placa e a porta e clique em **Carregar**.
4. Monitor serial: **115200 baud** nos três módulos.

## Comunicação por rádio (nRF24L01)

| Parâmetro | Valor |
|---|---|
| Canal | 108 |
| Taxa de dados | 1 Mbps |
| Potência | `RF24_PA_HIGH` |
| Payload | dinâmico, com auto-ACK |
| Endereço do Node 2 (aquisição) | `0xF0F0F0F002` |
| Endereço do Node 3 (controle) | `0xF0F0F0F003` |
| Endereço de resposta para a Central | `0xF0F0F0F0AA` |

### Pacote de dados dos sensores (Node 2 → Central, a cada 200 ms)

```
SN2 FFFFF TTTT PPPPP MMMM
```

| Campo | Variável | Escala |
|---|---|---|
| `SN2` | identificador do módulo de aquisição | – |
| `FFFFF` | vazão de perfusão | ml/min × 100 |
| `TTTT` | temperatura de perfusão (sensor de fluxo) | °C × 100 |
| `PPPPP` | pressão de perfusão | mmHg × 100 |
| `MMMM` | temperatura do tanque (MAX6675) | °C × 100 |

Exemplo: `SN2 03012 3745 04520 3680` → 30,12 ml/min; 37,45 °C; 45,20 mmHg; 36,80 °C.

## Lógica da Central (ESP32)

A cada pacote `SN2`, a Central:

1. **Verifica os limites de segurança** e aciona o alarme (LED vermelho + buzzer piscando a cada 250 ms) se:
   - temperatura de perfusão < 37,0 °C ou > 41,0 °C;
   - temperatura do tanque < 22,0 °C ou > 41,0 °C;
   - vazão fora de **setpoint ± 5 ml/min**;
   - pressão > 80 mmHg.
2. **Controla a vazão por PID** (Kp = 0,1; Ki = 0,05; Kd = 0,01; zona morta de ±2 ml/min; servo limitado a 0–90°), enviando `SERVO1:<ângulo>` ao Node 3 no máximo a cada 300 ms. Setpoint inicial: 40 ml/min.
3. **Controla a temperatura de perfusão** pelo relé 2 (bomba de água quente): desliga acima de 41,3 °C e religa abaixo de 39,3 °C.
4. **Controla a temperatura do tanque** pelo relé 1 (banho-maria): desliga acima de 40,0 °C e religa em 40,0 °C ou menos.

Se não chegar pacote por mais de 2 s, todos os LEDs e o buzzer são desligados.

### Comandos aceitos pela Central (USB serial ou Bluetooth "ESP32_Hub_Master")

| Comando | Efeito |
|---|---|
| `SET_FLUXO:<valor>` | Define o setpoint de vazão (5 a 100 ml/min) e os limites do alarme |
| `PID_ON` / `PID_OFF` | Liga/desliga o controle automático de vazão |
| qualquer outro texto | É repassado ao Node 3 (ver tabela abaixo) |

### Comandos aceitos pelo Node 3 (controle)

| Comando | Efeito | Resposta |
|---|---|---|
| `SERVO1:<0–180>` … `SERVO4:<0–180>` | Posiciona um servo | `N3:Pos1:<ângulo>` … |
| `SERVO:<0–180>` | Compatibilidade: posiciona o servo 2 | `N3:Pos:<ângulo>` |
| `SERVOn_DIR` / `SERVOn_ESQ` / `SERVOn_PARAR` | Servo *n* em 0°, 180° ou 90° | `N3:Dirn` … |
| `SERVO_DIR` / `SERVO_ESQ` / `SERVO_PARAR` | Os 4 servos juntos em 0°, 180° ou 90° | `N3:Servo Dir` … |
| `LIGAR_RELE` / `DESLIGAR_RELE` | Relé 1 (banho-maria do tanque) | `N3:Rele1 ON/OFF` |
| `LIGAR_RELE_2` / `DESLIGAR_RELE_2` | Relé 2 (bomba de água quente) | `N3:Rele2 ON/OFF` |
| `LER_ANGULO` | Lê o ângulo do encoder magnético AS5600 | `N3:<ângulo>` |
| outro | – | `N3:CMD_INVALIDO` |

Os relés são acionados em nível **LOW** (ligado = LOW).

## Pinagem

### Módulo de Aquisição – Arduino Nano (Node 2)

| Componente | Sinal | Pino |
|---|---|---|
| nRF24L01 | CE / CSN | D8 / D10 |
| nRF24L01 e MAX6675 (SPI compartilhado) | SCK / MOSI / MISO | D13 / D11 / D12 |
| MAX6675 (termopar tipo K) | CS | D2 |
| Sensor de pressão Honeywell ABPDANN005PG2A3 | I²C (end. `0x28`) | A4 (SDA) / A5 (SCL) |
| Sensor de fluxo Sensirion SLF3S-4000B | I²C (end. `0x08`) | A4 (SDA) / A5 (SCL) |

O MAX6675 é lido diretamente pelo SPI, sem biblioteca. O rádio é desligado (`powerDown`) durante a leitura para liberar o barramento.

### Módulo Central – ESP32-WROOM-32

| Componente | Função | GPIO |
|---|---|---|
| nRF24L01 | CE / CSN | 4 / 5 |
| nRF24L01 | SCK / MOSI / MISO (VSPI) | 18 / 23 / 19 |
| LED de status | Pacote `SN2` recebido (link de rádio ativo) | 12 |
| LED verde | Variáveis dentro da faixa (pisca a cada 500 ms) | 13 |
| LED amarelo | PID ativado (pisca a cada 1 s) | 14 |
| LED vermelho | Alerta (pisca com o buzzer) | 27 |
| Buzzer ativo | Alarme sonoro | 25 |
| Botão | Entrada com pull-up (reservado) | 32 |
| UART1 | RX / TX para Teensy (não usado neste projeto) | 16 / 15 |

### Módulo de Controle – Arduino Nano (Node 3)

| Componente | Função | Pino |
|---|---|---|
| nRF24L01 | CE / CSN | D9 / D10 |
| nRF24L01 | SCK / MOSI / MISO | D13 / D11 / D12 |
| Relé 1 | Banho-maria do tanque de imersão | D2 |
| Relé 2 | Bomba de circulação de água quente | D3 |
| Servo 1 (MG90S) | Válvula de fluxo da solução – comandado pelo PID | D5 |
| Servo 2 (MG995) | Válvula de gás carbogênico | D4 |
| Servo 3 (MG995) | Válvula de gás carbogênico | D6 |
| Servo 4 (MG995) | Válvula de gás carbogênico | D7 |
| Encoder magnético AS5600 | I²C – ângulo da válvula | A4 (SDA) / A5 (SCL) |

> Confira na montagem qual servo está em cada válvula: os comentários no código citam D4/D5 em ordem diferente da definição dos pinos.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `modulo_aquisicao_nano/modulo_aquisicao_nano.ino` | Configuração do rádio, temporização (200 ms) e montagem do pacote `SN2` |
| `modulo_aquisicao_nano/PressureSensor.*` | Leitura e conversão do sensor Honeywell (psi → mmHg) |
| `modulo_aquisicao_nano/FlowSensor.*` | Leitura do sensor Sensirion (vazão e temperatura) |
| `modulo_aquisicao_nano/Temp_Sensor.h`, `Temp_sensor.cpp` | Leitura do MAX6675 pelo SPI compartilhado com o rádio |
| `modulo_central_esp32/modulo_central_esp32.ino` | Inicialização, Bluetooth e leitura de comandos |
| `modulo_central_esp32/nrf24_control.*` | Rádio, limites de alarme, PID de vazão, controle dos relés e LEDs |
| `modulo_central_esp32/SistemaAlarme.*` | Configuração dos pinos de LEDs, buzzer e botão |
| `modulo_central_esp32/commands.*`, `foward_teensy.*` | Comandos de estimulação via Teensy herdados de outro projeto do HEartLab (não são chamados neste firmware) |
| `modulo_controle_nano/modulo_controle_nano.ino` | Recepção de comandos, servos, relés e encoder AS5600 |
