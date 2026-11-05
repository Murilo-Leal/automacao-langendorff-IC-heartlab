#ifndef SISTEMA_ALARME_H
#define SISTEMA_ALARME_H

#include <Arduino.h>

class SistemaAlarme {
  private:
    // Variáveis para guardar os pinos internamente
    int* _pinosLeds; // Ponteiro para o array
    int _qtdLeds;
    int _pinoBuzzer;
    int _pinoBotao;

  public:
    // Construtor
    SistemaAlarme(int* pinos, int qtd, int buzzer, int botao);

    // Nova função para configurar o hardware (pinMode)
    void begin(); 

    // Seus outros métodos (ex: processar, disparar, etc) continuam aqui...
    void processar();
};

#endif