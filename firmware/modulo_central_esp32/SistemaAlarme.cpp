#include "SistemaAlarme.h"

// --- CONSTRUTOR ---
// Apenas salva os valores, não roda pinMode ainda
SistemaAlarme::SistemaAlarme(int* pinos, int qtd, int buzzer, int botao) {
    _pinosLeds = pinos;   // Guarda o array
    _qtdLeds = qtd;       // Guarda a quantidade
    _pinoBuzzer = buzzer; // Guarda pino buzzer
    _pinoBotao = botao;   // Guarda pino botão
}

// --- FUNÇÃO BEGIN (INICIAR) ---
// Aqui colocamos a configuração de hardware
void SistemaAlarme::begin() {
    // Configura os LEDs
    for (int i = 0; i < _qtdLeds; i++) {
        pinMode(_pinosLeds[i], OUTPUT);
        digitalWrite(_pinosLeds[i], LOW);
    }

    // Configura Buzzer e Botão
    pinMode(_pinoBuzzer, OUTPUT);
    pinMode(_pinoBotao, INPUT_PULLUP);
    
    Serial.println("SistemaAlarme: Hardware configurado via CPP.");
}

// ... Suas outras funções (processar, etc) continuam abaixo ...