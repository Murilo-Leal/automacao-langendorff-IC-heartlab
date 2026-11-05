#include <Arduino.h>
#include <HardwareSerial.h>

HardwareSerial TeensySerial(1); // UART1 

void setupUART() {
  // Communication with Teensy
  TeensySerial.begin(115200, SERIAL_8N1, 16, 15); // RX=16, TX=15
  Serial.print("Teensy UART configured succesfully.");
}

void ForwardToTeensy(const String &comm) {
  // Forward computer commands to Teensy
    TeensySerial.println(comm);
}

void ForwardToComputer() {
  while(TeensySerial.available()) { 
    Serial.write(TeensySerial.read());
  }
}