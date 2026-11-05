#include "nrf24_control.h"

// --- PINAGEM DO ESP32 ---
#define CE_PIN    4
#define CSN_PIN   5
#define LED_STATUS 12   // Led de status do Watchdog / Link Rádio
#define LED_ALERTA 27   // Pino do LED Vermelho (Alerta)
#define ALARME_PIN 25   // Pino do Buzzer/Alarme
#define LED_AMARELO 14  // Pino do LED Amarelo (PID Ativado)
#define LED_VERDE  13   // Pino do LED Verde (Dados na faixa normal)


// --- CONTROLE DE TEMPO E WATCHDOG ---
unsigned long ultimaVezSN2 = 0;
unsigned long tempoAnteriorPID = 0;
unsigned long intervaloEnvioMinimo = 300; 
unsigned long ultimoEnvioServo = 0;

// Tempos para piscar os LEDs sem usar delay()
unsigned long ultimoPiscaAlarme = 0;     
unsigned long ultimoPiscaVerde = 0;      
unsigned long ultimoPiscaAmarelo = 0;    

// --- ESTADOS DO SISTEMA ---
bool releLigado = true;       // Rastreia o estado do Relé 2 (Fluxo)
bool releLigado2 = true;      // Rastreia o estado do Relé 1 (Tanque/Max)
bool sistemaEmAlerta = false; // Rastreia se há alguma anomalia crítica
bool pidAtivado = true;       // Flag para ligar/desligar o controle automático do Servo

// --- CONFIGURAÇÕES DO PID E ALARMES ---
float setpointFluxo = 40.0;      // Setpoint dinâmico de fluxo
float margemAlarmeFluxo = 5.0;   // NOVO: Tolerância do alarme (+ ou - o setpoint)

float Kp = 0.1;                
float Ki = 0.05;                 
float Kd = 0.01;                 

float erroAcumulado = 0;
float ultimoErro = 0;
int posicaoServoAtual = 45;      

RF24 radio(CE_PIN, CSN_PIN);

// =================================================================================
// ENDEREÇOS NRF24
// =================================================================================
const uint64_t nodeCmdAddr[6] = {
    0xF0F0F0F001LL, 0xF0F0F0F002LL, 0xF0F0F0F003LL, 
    0xF0F0F0F004LL, 0xF0F0F0F005LL, 0xF0F0F0F006LL
};
const uint64_t espResponsePipe = 0xF0F0F0F0AALL;

// =================================================================================
// FUNÇÃO PID MELHORADA COM DEADBAND
// =================================================================================
int calcularPID(float fluxoAtual) {
    unsigned long tempoAtual = millis();
    float dt = (tempoAtual - tempoAnteriorPID) / 1000.0;
    if (dt <= 0 || dt > 1.0) dt = 0.1;

    float erro = setpointFluxo - fluxoAtual;

    if (abs(erro) < 2.0) {
        erroAcumulado *= 0.95; 
        tempoAnteriorPID = tempoAtual;
        return posicaoServoAtual; 
    }

    float P = Kp * erro;
    
    erroAcumulado += erro * dt;
    erroAcumulado = constrain(erroAcumulado, -20, 20); 
    float I = Ki * erroAcumulado;
    
    float D = Kd * (erro - ultimoErro) / dt;
    
    float saida = P + I + D;

    ultimoErro = erro;
    tempoAnteriorPID = tempoAtual;

    int novaPosicao = constrain(posicaoServoAtual + (int)saida, 0, 90);
    
    return novaPosicao;
}

// =================================================================================
// CONFIGURAÇÃO DO RÁDIO E PINOS
// =================================================================================
void setupNRF24() {
    pinMode(LED_STATUS, OUTPUT);
    pinMode(LED_ALERTA, OUTPUT); 
    pinMode(ALARME_PIN, OUTPUT); 
    pinMode(LED_AMARELO, OUTPUT); 
    pinMode(LED_VERDE, OUTPUT);   

    SPI.begin();
    if (!radio.begin()) {
        Serial.println("ERRO CRITICO: NRF24L01 nao iniciado.");
    } else {
        Serial.println("Radio NRF24L01 Iniciado.");
    }

    radio.setPALevel(RF24_PA_HIGH);
    radio.setDataRate(RF24_1MBPS);
    radio.setChannel(108); 
    radio.enableDynamicPayloads();
    radio.setAutoAck(true);
    radio.setRetries(15, 15); 

    radio.openReadingPipe(0, espResponsePipe);
    for (int i = 0; i < 6; i++) {
        radio.openReadingPipe(i + 1, nodeCmdAddr[i]);
    }

    radio.startListening();
}

// =================================================================================
// LOOP DE VERIFICAÇÃO E LÓGICA DE CONTROLE
// =================================================================================
void verificarRadio() {
    uint8_t pipeNum;
    
    if (radio.available(&pipeNum)) {
        char buffer[40] = {0};
        uint8_t len = radio.getDynamicPayloadSize();
        if (len > 39) len = 39;
        radio.read(buffer, len);

        String msg = String(buffer);
        msg.trim();
        String prefixo = (pipeNum == 0) ? "RESP (Pipe 0) : " : "NODE " + String(pipeNum) + ": ";

        // IMPRIME A MENSAGEM COMPLETA NA SERIAL
        String log = prefixo + msg;
        Serial.println(log);

        // --- PROCESSAMENTO DOS DADOS DO SENSOR (NODE 2) ---
        if (msg.startsWith("SN2")) {
            int rawFlow, rawFlowTemp, rawPressure, rawMaxTemp;
            int contagem = sscanf(msg.c_str(), "SN2 %d %d %d %d", &rawFlow, &rawFlowTemp, &rawPressure, &rawMaxTemp);
            
            if (contagem == 4) {
                ultimaVezSN2 = millis(); 
                digitalWrite(LED_STATUS, HIGH); 

                float Flow = rawFlow / 100.0;
                float tempFluxo = rawFlowTemp / 100.0;
                float pressao = rawPressure / 100.0; 
                float tempMax = rawMaxTemp / 100.0;
                
                // Limites dinâmicos baseados no setpoint
                float minFluxo = setpointFluxo - margemAlarmeFluxo;
                float maxFluxo = setpointFluxo + margemAlarmeFluxo;
                
                // --- LÓGICA DE SEGURANÇA (VERIFICAÇÃO DE LIMITES) ---
                if ((tempFluxo < 37.0 || tempFluxo > 41.0) || 
                    (tempMax < 22.0 || tempMax > 41.0) || 
                    (Flow < minFluxo || Flow > maxFluxo) || // NOVO: Margem dinâmica do fluxo
                    (pressao > 80.0)) {
                    
                    if (!sistemaEmAlerta) {
                        Serial.println("\n!!! ALERTA DE SEGURANÇA ATIVADO !!!");
                        if (tempFluxo < 37.0 || tempFluxo > 41.0) Serial.printf("- Temp Fluxo fora: %.2f C\n", tempFluxo);
                        if (tempMax < 22.0 || tempMax > 41.0) Serial.printf("- Temp Tanque fora: %.2f C\n", tempMax);
                        if (Flow < minFluxo || Flow > maxFluxo) Serial.printf("- Fluxo fora da margem: %.2f (Aceitavel: %.2f a %.2f)\n", Flow, minFluxo, maxFluxo);
                        if (pressao > 80.0) Serial.printf("- Pressão crítica: %.2f\n", pressao);
                    }
                    sistemaEmAlerta = true;
                } else {
                    if (sistemaEmAlerta) {
                        Serial.println("\n-> Sistema normalizado. Alarme desligado.");
                        digitalWrite(LED_ALERTA, LOW);
                        digitalWrite(ALARME_PIN, LOW);
                    }
                    sistemaEmAlerta = false;
                }

                // --- CONTROLE DO SERVO (PID) ---
                if (pidAtivado) {
                    int posicaoCalculada = calcularPID(Flow);

                    if (posicaoCalculada != posicaoServoAtual && (millis() - ultimoEnvioServo > intervaloEnvioMinimo)) {
                        Serial.printf("Ajustando Servo: %d -> %d (Fluxo Atual: %.2f | Alvo: %.2f)\n", posicaoServoAtual, posicaoCalculada, Flow, setpointFluxo);
                        posicaoServoAtual = posicaoCalculada; 
                        String comandoPID = "SERVO1:" + String(posicaoServoAtual);
                        
                        if (sendNRF24MessageToNode(3, comandoPID)) {
                            ultimoEnvioServo = millis();
                        }
                    }
                }

                // --- CONTROLE TÉRMICO DO RELÉ 2 (FLUXO) ---
                if (tempFluxo > 41.3 && releLigado) {
                    if (sendNRF24MessageToNode(3, "DESLIGAR_RELE_2")) { 
                        releLigado = false;
                        Serial.printf("Alerta: Temp Fluxo %.2fC > 40C. Comando DESLIGAR_RELE_2 enviado.\n", tempFluxo);
                    }
                } 
                else if (tempFluxo <= 39.3 && !releLigado) {
                    if (sendNRF24MessageToNode(3, "LIGAR_RELE_2")) {
                        releLigado = true;
                        Serial.printf("Estabilizado: Temp Fluxo %.2fC. Comando LIGAR_RELE_2 enviado.\n", tempFluxo);
                    }
                }

                // --- CONTROLE TÉRMICO DO RELÉ 1 (TANQUE/MAX) ---
                if (tempMax > 40.0 && releLigado2) {
                    if (sendNRF24MessageToNode(3, "DESLIGAR_RELE_1")) { 
                        releLigado2 = false; 
                        Serial.printf("Alerta: Temp Max %.2fC > 40C. Comando DESLIGAR_RELE enviado.\n", tempMax);
                    }
                } 
                else if (tempMax <= 40.0 && !releLigado2) {
                    if (sendNRF24MessageToNode(3, "LIGAR_RELE_1")) {
                        releLigado2 = true; 
                        Serial.printf("Estabilizado: Temp Max %.2fC. Comando LIGAR_RELE enviado.\n", tempMax);
                    }
                }
            } 
        }
    }

    // =================================================================================
    // LÓGICA DE SINALIZAÇÃO VISUAL (PISCA-PISCA NÃO BLOQUEANTE)
    // =================================================================================
    unsigned long tempoAtualMillis = millis();
    bool recebendoDados = (tempoAtualMillis - ultimaVezSN2 <= 2000); 

    if (recebendoDados) {
        if (sistemaEmAlerta) {
            digitalWrite(LED_VERDE, LOW); 
            if (tempoAtualMillis - ultimoPiscaAlarme > 250) {
                ultimoPiscaAlarme = tempoAtualMillis;
                bool estadoAtual = !digitalRead(LED_ALERTA);
                digitalWrite(LED_ALERTA, estadoAtual);
                digitalWrite(ALARME_PIN, estadoAtual); 
            }
        } else {
            digitalWrite(LED_ALERTA, LOW);
            digitalWrite(ALARME_PIN, LOW);
            
            if (tempoAtualMillis - ultimoPiscaVerde > 500) {
                ultimoPiscaVerde = tempoAtualMillis;
                digitalWrite(LED_VERDE, !digitalRead(LED_VERDE));
            }
        }

        if (pidAtivado) {
            if (tempoAtualMillis - ultimoPiscaAmarelo > 1000) {
                ultimoPiscaAmarelo = tempoAtualMillis;
                digitalWrite(LED_AMARELO, !digitalRead(LED_AMARELO));
            }
        } else {
            digitalWrite(LED_AMARELO, LOW); 
        }

    } else {
        digitalWrite(LED_STATUS, LOW);
        digitalWrite(LED_VERDE, LOW);
        digitalWrite(LED_AMARELO, LOW);
        digitalWrite(LED_ALERTA, LOW);
        digitalWrite(ALARME_PIN, LOW);
    }
}

// =================================================================================
// FUNÇÃO DE ENVIO
// =================================================================================
bool sendNRF24MessageToNode(uint8_t nodeIndex, const String &msg) {
    if (nodeIndex < 1 || nodeIndex > 6) return false;

    radio.stopListening();
    radio.openWritingPipe(nodeCmdAddr[nodeIndex - 1]);
    bool ok = radio.write(msg.c_str(), msg.length() + 1);
    radio.startListening();

    if (!ok) Serial.printf("!!! Falha ao contatar NODE %d\n", nodeIndex);
    return ok;
}

// =================================================================================
// LÓGICA DO MONITOR SERIAL (COMANDOSSE MANUAIS E DINÂMICOS)
// =================================================================================
void verificarSerial() {
    if (Serial.available() > 0) {
        String comandoSerial = Serial.readStringUntil('\n');
        comandoSerial.trim(); 

        if (comandoSerial.length() > 0) {
            
            if (comandoSerial.startsWith("SET_FLUXO:")) {
                String valorStr = comandoSerial.substring(10); 
                float novoSetpoint = valorStr.toFloat();
                
                if (novoSetpoint > 5.0 && novoSetpoint < 100.0) { 
                    setpointFluxo = novoSetpoint;
                    Serial.printf("\n=========================================\n");
                    Serial.printf("-> NOVO SETPOINT DE FLUXO DEFINIDO: %.2f\n", setpointFluxo);
                    Serial.printf("-> LIMITES DO ALARME ATUALIZADOS: %.2f a %.2f\n", 
                                  (setpointFluxo - margemAlarmeFluxo), (setpointFluxo + margemAlarmeFluxo));
                    Serial.printf("=========================================\n\n");
                } else {
                    Serial.println("-> ERRO: Valor de setpoint invalido. Use algo entre 5.0 e 100.0");
                }
                return; 
            }

            if (comandoSerial == "PID_ON") {
                pidAtivado = true;
                Serial.println("-> Controle PID ATIVADO.");
                return;
            }
            if (comandoSerial == "PID_OFF") {
                pidAtivado = false;
                Serial.println("-> Controle PID DESATIVADO (Modo Manual).");
                return;
            }

            Serial.println("COMANDO MANUAL RECEBIDO: " + comandoSerial);
            
            if (sendNRF24MessageToNode(3, comandoSerial)) {
                Serial.println("-> Comando manual enviado com sucesso!");
                
                if (comandoSerial == "LIGAR_RELE_1") releLigado2 = true;
                if (comandoSerial == "DESLIGAR_RELE_1") releLigado2 = false;
                if (comandoSerial == "LIGAR_RELE_2") releLigado = true;
                if (comandoSerial == "DESLIGAR_RELE_2") releLigado = false;
            } else {
                Serial.println("-> Falha ao enviar comando manual.");
            }
        }
    }
}