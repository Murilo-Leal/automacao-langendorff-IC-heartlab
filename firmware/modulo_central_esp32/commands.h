#ifndef STIM_COMMANDS_H
#define STIM_COMMANDS_H

#include <Arduino.h>

// Initializes the serial interface for STIM commands
void setupSerialCommands();

// Processes received serial commands related to STIM
void processSerialCommand();

#endif
