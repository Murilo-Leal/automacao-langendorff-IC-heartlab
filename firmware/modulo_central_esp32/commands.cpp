#include "commands.h"
#include "foward_teensy.h"
#include "nrf24_control.h" 

void setupSerialCommands() {
    Serial.begin(115200);
    while (!Serial) {
        delay(10); // Wait for Serial to initialize
    }
    Serial.println("Serial Commands Ready");
    setupNRF24(); // Initialize NRF24L01
}

void processSerialCommand() {
    if (Serial.available()) {
        String command = Serial.readStringUntil('\n');
        command.trim();
        Serial.print("Received command: ");
        Serial.println(command);

        if (command.equals("ESP RESTART")){
          ESP.restart();
        }
        
        if (command.startsWith("START_CONTINUOUS")) {
            ForwardToTeensy(command);
            // Serial.println("S0 mode started ESP.");
        } else if (command.startsWith("STOP_CONTINUOUS")) {
            ForwardToTeensy(command);
            // Serial.println("S0 mode stopped ESP.");
        } else if (command.startsWith("START_BURST")) {
            ForwardToTeensy(command);
            // Serial.println("Burst mode started ESP.");
        } else if (command.startsWith("STOP_BURST")) {
            ForwardToTeensy(command);
            // Serial.println("Burst mode stopped ESP.");
        } else if (command.startsWith("SET_PARAMS")) {
            uint8_t type;
            uint32_t pulseWidthMs;
            uint32_t periodMs;
            uint8_t pulseCount;
            String enableStr;

            int firstSpace = command.indexOf(' ');
            int secondSpace = command.indexOf(' ', firstSpace + 1);
            int thirdSpace = command.indexOf(' ', secondSpace + 1);
            int fourthSpace = command.indexOf(' ', thirdSpace + 1);
            int fifthSpace = command.indexOf(' ', fourthSpace + 1);

            if (fifthSpace > 0) {
                ForwardToTeensy(command);
                bool enabled = (enableStr == "ON");
                // Serial.printf("Parameters set for S%d: Pulse Width=%d ms, Period=%d ms, Pulse Count=%d, Enabled=%s\n",
                              // type-1, pulseWidthMs, periodMs, pulseCount, enabled ? "ON" : "OFF");
            } else {
                Serial.println("Invalid SET_PARAMS command format.");
            }
        } else if (command.startsWith("SEND_ARDUINO")) {
            int firstSpace = command.indexOf(' ');
            int secondSpace = command.indexOf(' ', firstSpace + 1);

            if (secondSpace > 0) {
                uint8_t arduinoIndex = command.substring(firstSpace + 1, secondSpace).toInt();
                String message = command.substring(secondSpace + 1);

                if (!sendNRF24MessageToNode(arduinoIndex, message)) {
                    Serial.println("Failed to send message to Arduino.");
                }
            } else {
                Serial.println("Invalid SEND_ARDUINO command format. Use: SEND_ARDUINO X YYYYYYYY");
            }
        } else if (command.startsWith("SET_SYNC")) {
              ForwardToTeensy(command);
          } else if (command.startsWith("SYNC_START")) {
              ForwardToTeensy(command);
          } else if (command.startsWith("SYNC_STOP")) {
              ForwardToTeensy(command);
          } else if (command.startsWith("SYNC_REC")) {
              ForwardToTeensy(command);
          } else {
              Serial.println("Unknown SYNC command.");
          }
    }
}
