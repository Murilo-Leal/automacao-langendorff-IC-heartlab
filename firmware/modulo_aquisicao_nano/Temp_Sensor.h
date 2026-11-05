#ifndef TEMPSENSOR_H
#define TEMPSENSOR_H

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h> // Necessário pois passaremos o rádio como referência

// Configura o pino do sensor
void setupTempSensor(int csPin);

// Lê a temperatura gerenciando o conflito de SPI com o rádio
// Recebe o pino do sensor e o objeto do rádio por referência (&radio)
float readTempSensor(int csPin, RF24 &radio);

#endif