# Multi-Sensor Data Aggregator

## Components

#### 1\. Raspberry Pi EMQX003

It's a single-board computer that can handle more complex tasks like data processing, networking, or even controlling other devices.

**What to do**: Set up your Raspberry Pi and make sure it has Raspbian (or another OS) installed. You can connect it to your network, set up SSH, and use it to send/receive data to/from your sensors.



#### 2\. Arduino Nano ESP32

The Arduino Nano ESP32 will be the microcontroller handling the sensors and performing real-time tasks like reading data from sensors and processing it.

**What to do**: Connect the Arduino to your Raspberry Pi via USB (for initial programming). Once programmed, it can operate wirelessly (if you need to) via WiFi (thanks to ESP32).



#### 3\. Breadboard

The breadboard is where you'll wire everything together without soldering. It helps you create temporary connections to test your circuit.

**What to do**: Place all your components here and make sure to connect the power, ground, and signal lines appropriately.



#### 4\. MB102 Breadboard Power Supply Module

This module will supply power to your breadboard and components. It's an easy way to distribute power for your sensors and microcontrollers.

What to do: Insert this into your breadboard. It typically has both 5V and 3.3V outputs, so connect the appropriate power lines to the components that need it (e.g., Arduino uses 5V, while some sensors might need 3.3V).



#### 5\. Resistors

Resistors limit the current flowing through your components to prevent them from burning out.

**What to do**: Use resistors where necessary. For example, you may need a resistor for your PIR sensor to ensure it receives the correct amount of current.



#### 6\. PIR Motion Sensor

The PIR (Passive InfraRed) sensor detects movement. It can be used to trigger an event when motion is detected.

**What to do**: Connect the sensor’s power pins (VCC, GND) to the breadboard power supply, and the output pin to a digital input pin on the Arduino (e.g., D2). The Arduino will check for a HIGH signal to detect motion.



#### 7\. Temperature and Humidity Sensor (e.g., DHT11 or DHT22)

This sensor will read the temperature and humidity in the environment.

**What to do**: Connect the sensor’s VCC and GND to the breadboard power, and the signal pin to a digital input pin on the Arduino (e.g., D3). The Arduino can read temperature and humidity via a library in the code.



#### 8\. Ultrasonic Ranger

This sensor measures distance by sending out sound waves and measuring how long it takes for the waves to bounce back. It’s useful for detecting how far away an object is.

**What to do**: The ultrasonic sensor will have a Trigger and Echo pin. Connect the Trigger pin to a digital output pin on the Arduino (e.g., D4), and the Echo pin to a digital input pin (e.g., D5). Your Arduino will send a pulse via the Trigger pin, then measure the time it takes for the Echo pin to receive the reflected sound.

