#include "PressureSensor.h"
#include <Wire.h>

#define PRESSURE_ADDR 0x28 // Endereço I²C do sensor Honeywell ABPDANN005PG2A3

bool setupPressureSensor() {
    Wire.begin();
    delay(100);
    Serial.println("Sensor de pressão inicializado.");
    return true;
}

float readPressureMMHG() {
    Wire.beginTransmission(PRESSURE_ADDR);
    Wire.endTransmission();
    Wire.requestFrom(PRESSURE_ADDR, 4);

    if (Wire.available() < 4) {
        Serial.println("Falha na leitura do sensor de pressão!");
        return NAN;
    }

    uint8_t msb = Wire.read();
    uint8_t lsb = Wire.read();
    uint8_t t_msb = Wire.read();
    uint8_t t_lsb = Wire.read();

    // Conversão segundo o datasheet Honeywell TruStability ABP
    uint16_t rawPressure = ((uint16_t)msb << 8) | lsb;
    float pressureCounts = rawPressure & 0x3FFF; // bits 13:0
    float pressurePSI = ((pressureCounts - 1638.0) * (5.0 / (14745.0 - 1638.0))); // 0–5 psi
    float pressureMMHG = pressurePSI * 51.7149; // 1 psi = 51.7149 mmHg

    return pressureMMHG;
}
