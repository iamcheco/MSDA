#include "SensorHub.hpp"

void setup() {
    SensorHub::begin(115200);
}

void loop() {
    SensorHub::update();
}
