/*
 * Projeto: Automação do setup experimental para o estudo de arritmias cardíacas
 * HEartLab – Universidade Federal do ABC | FAPESP 2025/22698-7
 * Autor:   Murilo Leal Santos
 *
 * Módulo:  Controle – atuadores (Node 3)
 * Placa:   Arduino Nano + nRF24L01
 * Versão de origem: Node3_Atuador_Sensor_4Servos
 * Detalhes de pinagem, comandos e bibliotecas: firmware/README.md
 */

/*
    NODE 3 - ATUADOR + SENSOR AS5600 (4 SERVOS)
*/

#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>
#include <Servo.h>
#include <Wire.h>
#include <AS5600.h>

// --- PINOS ---
#define PIN_RELE_1 2
#define PIN_RELE_2 3
#define PIN_SERVO_1 5
#define PIN_SERVO_2 4
#define PIN_SERVO_3 6
#define PIN_SERVO_4 7
#define CE_PIN    9
#define CSN_PIN   10

// --- ENDEREÇOS ---
const uint64_t RX_ADDRESS = 0xF0F0F0F003LL;
const uint64_t TX_ADDRESS = 0xF0F0F0F0AALL;

RF24 radio(CE_PIN, CSN_PIN);

// --- SERVOS ---
Servo servo1; // D4
Servo servo2; // D5 (era o "servoMotor" original)
Servo servo3; // D6
Servo servo4; // D7

AS5600 as5600;

void enviarResposta(const char* texto) {
    char resposta[32];
    snprintf(resposta, sizeof(resposta), "N3:%s", texto);

    radio.stopListening();
    delayMicroseconds(150);

    bool ok = radio.write(resposta, strlen(resposta) + 1);

    radio.startListening();

    if (ok) {
        Serial.print("Resposta enviada: ");
        Serial.println(resposta);
    } else {
        Serial.println("Falha no envio");
    }
}

float lerAnguloAS5600() {
    uint16_t raw = as5600.readAngle();   // 0 a 4095
    float angulo = raw * 360.0 / 4096.0;
    return angulo;
}

// Move um servo específico para um ângulo, com segurança e resposta padronizada
void moverServo(Servo &servo, int angulo, const char* nomeServo) {
    angulo = constrain(angulo, 0, 180);
    servo.write(angulo);

    char feedback[24];
    snprintf(feedback, sizeof(feedback), "%s:%d", nomeServo, angulo);
    enviarResposta(feedback);
}

// Move os 4 servos juntos para o mesmo ângulo
void moverTodosServos(int angulo, const char* nomeResposta) {
    angulo = constrain(angulo, 0, 180);
    servo1.write(angulo);
    servo2.write(angulo);
    servo3.write(angulo);
    servo4.write(angulo);
    enviarResposta(nomeResposta);
}

void setup() {
    Serial.begin(115200);

    // --- RELÉS ---
    pinMode(PIN_RELE_1, OUTPUT);
    pinMode(PIN_RELE_2, OUTPUT);
    digitalWrite(PIN_RELE_1, HIGH);
    digitalWrite(PIN_RELE_2, HIGH);

    // --- SERVOS ---
    servo1.attach(PIN_SERVO_1);
    servo2.attach(PIN_SERVO_2);
    servo3.attach(PIN_SERVO_3);
    servo4.attach(PIN_SERVO_4);

    servo1.write(90);
    servo2.write(90);
    servo3.write(90);
    servo4.write(90);

    // --- AS5600 ---
    Wire.begin();
    if (!as5600.begin()) {
        Serial.println("AS5600 nao detectado!");
        // while (1); // Removido para permitir que o rádio funcione mesmo sem sensor
    } else {
        Serial.println("AS5600 pronto");
    }

    // --- RADIO ---
    if (!radio.begin()) {
        Serial.println("ERRO: NRF24L01");
        while (1);
    }

    radio.setPALevel(RF24_PA_HIGH);
    radio.setDataRate(RF24_1MBPS);
    radio.setChannel(108);
    radio.enableDynamicPayloads();
    radio.setAutoAck(true);

    radio.openReadingPipe(1, RX_ADDRESS);
    radio.openWritingPipe(TX_ADDRESS);

    radio.startListening();

    Serial.println("NODE 3 Iniciado (4 servos).");
}

void loop() {
    if (radio.available()) {
        char cmd[32] = {0};
        uint8_t len = radio.getDynamicPayloadSize();
        if (len > 31) len = 31;

        radio.read(&cmd, len);
        cmd[len] = '\0'; // Garante que a string termina corretamente

        Serial.print("Comando Recebido: ");
        Serial.println(cmd);

        // --- LÓGICA DE COMANDOS ---

        // 1. Comandos de Posição Direta para cada servo (SERVO1:XXX ... SERVO4:XXX)
        if (strncmp(cmd, "SERVO1:", 7) == 0) {
            int angulo = atoi(&cmd[7]);
            moverServo(servo1, angulo, "Pos1");
        }
        else if (strncmp(cmd, "SERVO2:", 7) == 0) {
            int angulo = atoi(&cmd[7]);
            moverServo(servo2, angulo, "Pos2");
        }
        else if (strncmp(cmd, "SERVO3:", 7) == 0) {
            int angulo = atoi(&cmd[7]);
            moverServo(servo3, angulo, "Pos3");
        }
        else if (strncmp(cmd, "SERVO4:", 7) == 0) {
            int angulo = atoi(&cmd[7]);
            moverServo(servo4, angulo, "Pos4");
        }

        // 1b. Compatibilidade com comando antigo "SERVO:XXX" -> controla o servo 2 (pino 5, o original)
        else if (strncmp(cmd, "SERVO:", 6) == 0) {
            int angulo = atoi(&cmd[6]);
            moverServo(servo2, angulo, "Pos");
        }

        // 2. Comandos de Relé
        else if (strcmp(cmd, "LIGAR_RELE") == 0) {
            digitalWrite(PIN_RELE_1, LOW);
            enviarResposta("Rele1 ON");
        }
        else if (strcmp(cmd, "DESLIGAR_RELE") == 0) {
            digitalWrite(PIN_RELE_1, HIGH);
            enviarResposta("Rele1 OFF");
        }
        else if (strcmp(cmd, "LIGAR_RELE_2") == 0) {
            digitalWrite(PIN_RELE_2, LOW);
            enviarResposta("Rele2 ON");
        }
        else if (strcmp(cmd, "DESLIGAR_RELE_2") == 0) {
            digitalWrite(PIN_RELE_2, HIGH);
            enviarResposta("Rele2 OFF");
        }

        // 3. Comandos de Direção Fixa (agora aplicados aos 4 servos simultaneamente)
        else if (strcmp(cmd, "SERVO_DIR") == 0) {
            moverTodosServos(0, "Servo Dir");
        }
        else if (strcmp(cmd, "SERVO_ESQ") == 0) {
            moverTodosServos(180, "Servo Esq");
        }
        else if (strcmp(cmd, "SERVO_PARAR") == 0) {
            moverTodosServos(90, "Servo Stop");
        }

        // 3b. Comandos de Direção Fixa INDIVIDUAIS (por servo)
        else if (strcmp(cmd, "SERVO1_DIR") == 0) {
            moverServo(servo1, 0, "Dir1");
        }
        else if (strcmp(cmd, "SERVO1_ESQ") == 0) {
            moverServo(servo1, 180, "Esq1");
        }
        else if (strcmp(cmd, "SERVO1_PARAR") == 0) {
            moverServo(servo1, 90, "Stop1");
        }
        else if (strcmp(cmd, "SERVO2_DIR") == 0) {
            moverServo(servo2, 0, "Dir2");
        }
        else if (strcmp(cmd, "SERVO2_ESQ") == 0) {
            moverServo(servo2, 180, "Esq2");
        }
        else if (strcmp(cmd, "SERVO2_PARAR") == 0) {
            moverServo(servo2, 90, "Stop2");
        }
        else if (strcmp(cmd, "SERVO3_DIR") == 0) {
            moverServo(servo3, 0, "Dir3");
        }
        else if (strcmp(cmd, "SERVO3_ESQ") == 0) {
            moverServo(servo3, 180, "Esq3");
        }
        else if (strcmp(cmd, "SERVO3_PARAR") == 0) {
            moverServo(servo3, 90, "Stop3");
        }
        else if (strcmp(cmd, "SERVO4_DIR") == 0) {
            moverServo(servo4, 0, "Dir4");
        }
        else if (strcmp(cmd, "SERVO4_ESQ") == 0) {
            moverServo(servo4, 180, "Esq4");
        }
        else if (strcmp(cmd, "SERVO4_PARAR") == 0) {
            moverServo(servo4, 90, "Stop4");
        }

        // 4. Sensor AS5600
        else if (strcmp(cmd, "LER_ANGULO") == 0) {
            float ang = lerAnguloAS5600();
            char buffer[20];
            dtostrf(ang, 5, 2, buffer);
            enviarResposta(buffer);
        }

        else {
            enviarResposta("CMD_INVALIDO");
        }
    }
}
