#ifndef NRF24_CONTROL_H
#define NRF24_CONTROL_H
#define LED_INDICADOR_NODE2  13

#include <Arduino.h>
#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>
#include "BluetoothSerial.h"
#include "SistemaAlarme.h" 

// Permite que outros arquivos acessem o Bluetooth
extern BluetoothSerial SerialBT;


// --- Protótipos das Funções
void setupNRF24();
void verificarRadio();
void verificarSerial();
bool sendNRF24MessageToNode(uint8_t nodeIndex, const String &msg);
 
// Declaração externa para usar o objeto alarme no main se precisar
extern SistemaAlarme alarme;

#endif
