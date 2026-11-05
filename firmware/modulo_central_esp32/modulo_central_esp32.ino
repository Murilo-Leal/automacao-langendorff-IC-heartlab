/*
 * Projeto: Automação do setup experimental para o estudo de arritmias cardíacas
 * HEartLab – Universidade Federal do ABC | FAPESP 2025/22698-7
 * Autor:   Murilo Leal Santos
 *
 * Módulo:  Central de Comunicação
 * Placa:   ESP32-WROOM-32 + nRF24L01
 * Versão de origem: ESP_Central_Compativel_14_Dinamico
 * Detalhes de pinagem, comandos e bibliotecas: firmware/README.md
 */

#include <Arduino.h>
#include "BluetoothSerial.h"
#include "nrf24_control.h" 
#include "commands.h" 
#include "SistemaAlarme.h"

// --- DEFINIÇÃO DOS PINOS ---
// Esta variável precisa existir aqui para ser passada para o alarme
int pinosLeds[] = {12, 13, 14, 27}; 

// Instância Global do Alarme e Leds
SistemaAlarme alarme(pinosLeds, 4, 25, 32);

// Instância Global do Bluetooth
BluetoothSerial SerialBT;

void setup() {
    // Inicia o sistema
    Serial.begin(115200);
    Serial.setTimeout(50);

    if (!SerialBT.begin("ESP32_Hub_Master")) {
        Serial.println("Erro Bluetooth");
    } else {
        Serial.println("Bluetooth ON.");
    }

     // Função que criamos na Classe Sistema Alarme
    alarme.begin(); 

    pinMode(LED_INDICADOR_NODE2, OUTPUT);

    setupNRF24();
    // setupSerialCommands(); // Comentado para evitar conflito
    setupNRF24();
    
    Serial.println("Sistema Pronto.");
    Serial.println("Digite comandos: LIGAR_RELE_1_2, DESLIGAR_RELE_1_2, SERVO_DIR...");
}

void loop() {
    // 1. Checa o Rádio (respostas e sensores)
    verificarRadio();
    verificarSerial();

    // 2. LÊ SERIAL DO PC (Modo Simples - Bypass no commands.cpp)
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim(); // Remove espaços e quebra de linha
        
        if (cmd.length() > 0) {
            // Força envio para o Node 3 (Atuador)
            // Se quiser mudar o node, mude o número 3 para outro ID
            sendNRF24MessageToNode(3, cmd); 
        }
    }

    // 3. LÊ BLUETOOTH (Modo Simples)
    if (SerialBT.available()) {
        String cmd = SerialBT.readStringUntil('\n');
        cmd.trim();
        
        if (cmd.length() > 0) {
            sendNRF24MessageToNode(3, cmd);
        }
    }
}
