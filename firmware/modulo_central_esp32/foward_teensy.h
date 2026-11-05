#ifndef STIM_CONTROL_H
#define STIM_CONTROL_H

#include <Arduino.h>

void setupUART();
void ForwardToTeensy(const String &comm);
void ForwardToComputer();

#endif
