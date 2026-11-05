#ifndef FLOWSENSOR_H
#define FLOWSENSOR_H

#include <Arduino.h>

// Inicializa o sensor de fluxo e temperatura do fluido (SLF3S-4000B)
bool setupFlowSensor();

// Faz a leitura dos valores de fluxo (ml/min) e temperatura (°C)
// Retorna true se a leitura foi bem-sucedida
bool readFlowSensor(float &flowRate, float &fluidTemp);

#endif