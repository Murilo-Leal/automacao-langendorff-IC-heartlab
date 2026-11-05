#ifndef PRESSURESENSOR_H
#define PRESSURESENSOR_H

#include <Arduino.h>

// Inicializa o sensor de pressão (Honeywell ABPDANN005PG2A3)
bool setupPressureSensor();

// Lê a pressão e retorna em mmHg
float readPressureMMHG();

#endif