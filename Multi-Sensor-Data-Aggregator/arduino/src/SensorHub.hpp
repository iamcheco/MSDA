#ifndef SENSOR_HUB_HPP
#define SENSOR_HUB_HPP

#include <Arduino.h>

/**
 * Arduino Nano Sensor Hub
 *
 * Auto-detects attached sensors (DHT11/22, DS18B20, BMP280, HC-SR04, analog inputs)
 * and streams JSON-encoded messages over Serial.
 *
 * Provides inventory, data, heartbeat, log, and error messages.
 * Accepts commands (PING, INVENTORY, START, STOP, SET_RATE <ms>, STATUS, RESET).
 */

class SensorHub {
public:
    /**
     * Initialize serial, detect sensors, and send inventory + heartbeat.
     *
     * :param baudrate: UART speed (default 115200).
     * :return : of objects.
     * :return: None.
     */
    static void begin(unsigned long baudrate = 115200);

    /**
     * Main loop: handles commands, sampling, and heartbeats.
     *
     * :return : of objects.
     * :return: None.
     */
    static void update();
};

#endif // SENSOR_HUB_HPP
