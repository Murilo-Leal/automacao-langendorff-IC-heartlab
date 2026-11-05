/*
 * Projeto: Automação do setup experimental para o estudo de arritmias cardíacas
 * HEartLab – Universidade Federal do ABC | FAPESP 2025/22698-7
 * Autor:   Murilo Leal Santos
 *
 * Módulo:  Aquisição de Dados dos Sensores (Node 2)
 * Placa:   Arduino Nano + nRF24L01
 * Versão de origem: SensorData_Compativel_5
 * Detalhes de pinagem, comandos e bibliotecas: firmware/README.md
 */

#include <SPI.h>
#include <Arduino.h>
#include <nRF24L01.h>
#include <RF24.h>
// Seus includes de sensores
#include "PressureSensor.h"
#include "FlowSensor.h"
#include "Temp_Sensor.h"

// PINOS NODE 2
#define CE_PIN       8  
#define CSN_PIN      10
#define CS_MAX6675   2   

RF24 radio(CE_PIN, CSN_PIN);

const uint64_t addrNode2 = 0xF0F0F0F002LL; 

unsigned long lastSendTime = 0;
const int sendInterval = 200; 
unsigned long lastTempReadTime = 0;
int max6675Value = 0;

void setup() {
    Serial.begin(115200);
    SPI.begin();
    
    setupPressureSensor();
    setupFlowSensor();
    setupTempSensor(CS_MAX6675); 

    if (!radio.begin()) {
        Serial.println("ERRO Radio Node 2");
        while (1);
    }
    
    radio.setPALevel(RF24_PA_HIGH);      
    radio.setDataRate(RF24_1MBPS);      
    radio.setChannel(108);              
    radio.enableDynamicPayloads();      
    radio.setAutoAck(true);             
    
    radio.openWritingPipe(addrNode2);     
    radio.stopListening();              
}

void loop() {
    unsigned long now = millis();

    // Leitura Temp
    if (now - lastTempReadTime >= 200) {
        lastTempReadTime = now;
        float rawTemp = readTempSensor(CS_MAX6675, radio);
        if (rawTemp > -900) max6675Value = (int)(rawTemp * 100);
    }

    // Envio
    if (now - lastSendTime >= sendInterval) {
        lastSendTime = now;

        float pressure = readPressureMMHG();
        float flowRate, flowTemp; 
        readFlowSensor(flowRate, flowTemp); 
        
        // Formata mensagem: SN2 [Fluxo] [TempFluxo] [Pressão] [TempMAX]
        char message[40] = {0};
        snprintf(message, sizeof(message), "SN2 %05d %04d %05d %04d", 
                 (int)(flowRate * 100), (int)(flowTemp * 100), 
                 (int)(pressure * 100), max6675Value);

        if (radio.write(message, strlen(message))) {
             // Sucesso silencioso ou debug
        }
    }
}