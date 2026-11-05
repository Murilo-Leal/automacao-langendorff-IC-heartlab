#include "Temp_Sensor.h"

void setupTempSensor(int csPin) {
    // Configura o pino CS como saída e o desativa (HIGH)
    pinMode(csPin, OUTPUT);
    digitalWrite(csPin, HIGH);
}

float readTempSensor(int csPin, RF24 &radio) {
    uint16_t v;

    // 1. Pausa o rádio para liberar o barramento SPI
    radio.powerDown(); 
    
    // 2. Inicia comunicação com o MAX6675
    digitalWrite(csPin, LOW);
    delayMicroseconds(10); // Pequena estabilização

    // O MAX6675 envia 16 bits
    v = SPI.transfer(0x00) << 8;
    v |= SPI.transfer(0x00);

    // Finaliza comunicação com o sensor
    digitalWrite(csPin, HIGH);
    
    // 3. Religa o rádio
    radio.powerUp();
    // IMPORTANTE: O nRF24L01 precisa de ~1.5ms a 5ms para acordar
    delay(5); 

    // 4. Verifica bit D2 (indica se termopar está desconectado)
    if (v & 0x4) {
        return -999.0; // Código de erro
    }

    // 5. Calcula temperatura (bits D14-D3)
    // Desloca 3 bits para direita e multiplica pela resolução (0.25°C)
    return (v >> 3) * 0.25;
}