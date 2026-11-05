#include "FlowSensor.h"
#include <Wire.h>
#include <SensirionI2cSf06Lf.h>

// Objeto do sensor de fluxo (SLF3S-4000B)
SensirionI2cSf06Lf flowSensor;
#define FLOW_SENSOR_ADDR 0x08

bool setupFlowSensor() {
    Wire.begin();
    delay(100);

    flowSensor.begin(Wire, FLOW_SENSOR_ADDR);

    uint32_t productIdentifier;
    uint8_t serialNumber[8];
    int16_t error;

    // Novo formato da função
    error = flowSensor.readProductIdentifier(productIdentifier, serialNumber, sizeof(serialNumber));
    if (error) {
        Serial.print("Erro ao detectar sensor de fluxo: ");
        Serial.println(error);
        return false;
    }

    Serial.print("Sensor de fluxo detectado. Product ID: 0x");
    Serial.println(productIdentifier, HEX);

    // Inicia medição contínua de água (pré-calibração do SLF3S-4000B)
    flowSensor.startH2oContinuousMeasurement();
    delay(50);

    return true;
}

bool readFlowSensor(float &flowRate, float &fluidTemp) {
    float flow = 0.0f;
    float temperature = 0.0f;
    uint16_t raw = 0;

    // Usa escala de calibração para água
    int16_t error = flowSensor.readMeasurementData(INV_FLOW_SCALE_FACTORS_LD20_2600B, flow, temperature, raw);
    if (error) {
        Serial.print("Erro na leitura do fluxo: ");
        Serial.println(error);
        return false;
    }

    flowRate = flow;
    fluidTemp = temperature;
    return true;

    // Conversão já vem em ml/min e °C
    flowRate = flow;
    fluidTemp = temperature;

    return true;
}
