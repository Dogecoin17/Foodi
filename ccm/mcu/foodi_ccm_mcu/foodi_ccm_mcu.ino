// Foodi CCM – MCU firmware for the Arduino UNO Q (STM32 side).
//
// Responsibilities (real-time, independent of Linux):
//   - case temperature from a BMP280 (I2C)
//   - cooling fans with hysteresis; fail-safe = fans ON if the sensor fails
//   - status LEDs: ON at boot, two connection LEDs driven from Linux
//   - watchdog: if Linux stops calling for WATCHDOG_MS, blink the conn LEDs
//
// Linux talks to this sketch over the Arduino Bridge (RPC):
//   get_temp()  -> float  degrees C
//   fan_on()    -> bool
//   set_conn_leds(bool feeder, bool wifi)
//
// Wiring notes:
//   - power LED and the main switch are hard-wired (5 V rail), no MCU needed
//   - HX-3S-01 BMS is protection-only, no data lines
//   - both 40 mm fans share one PWM pin through a transistor/MOSFET stage
//   - LEDs with series resistors, active HIGH
#include <Arduino_RouterBridge.h>
#include <Wire.h>
#include <Adafruit_BMP280.h>

constexpr int PIN_FAN = 9;        // PWM, both fans via driver stage
constexpr int PIN_LED_ON = 2;     // lit while the MCU runs
constexpr int PIN_LED_FEEDER = 3; // feeder (BLE) link
constexpr int PIN_LED_WIFI = 4;   // local network link

constexpr float FAN_ON_C = 50.0f;  // hysteresis: on above this
constexpr float FAN_OFF_C = 45.0f; // off below this
constexpr uint8_t FAN_PWM = 255;
constexpr uint32_t WATCHDOG_MS = 10000;

Adafruit_BMP280 bmp; // I2C, address 0x76 or 0x77 (auto-detected)
bool bmpOk = false;
bool fanOn = false;
bool ledFeeder = false;
bool ledWifi = false;
uint32_t lastLinuxCmdMs = 0;

void setFan(bool on)
{
  fanOn = on;
  analogWrite(PIN_FAN, on ? FAN_PWM : 0);
}

// ---- Bridge RPC entry points (called from Linux) ------------------------------
float get_temp()
{
  return bmpOk ? bmp.readTemperature() : NAN;
}

bool fan_on()
{
  return fanOn;
}

void set_conn_leds(bool feeder, bool wifi)
{
  ledFeeder = feeder;
  ledWifi = wifi;
  lastLinuxCmdMs = millis(); // feed the watchdog
}

void setup()
{
  pinMode(PIN_FAN, OUTPUT);
  setFan(false);
  pinMode(PIN_LED_ON, OUTPUT);
  pinMode(PIN_LED_FEEDER, OUTPUT);
  pinMode(PIN_LED_WIFI, OUTPUT);
  digitalWrite(PIN_LED_ON, HIGH); // "on" LED

  bmpOk = bmp.begin(0x76) || bmp.begin(0x77);
  if (!bmpOk)
    setFan(true); // cannot measure temperature -> cool anyway

  Bridge.begin();
  Bridge.provide_safe("get_temp", get_temp);
  Bridge.provide_safe("fan_on", fan_on);
  Bridge.provide_safe("set_conn_leds", set_conn_leds);
}

void loop()
{
  if (bmpOk)
  {
    float t = bmp.readTemperature();
    if (!fanOn && t >= FAN_ON_C)
      setFan(true);
    else if (fanOn && t <= FAN_OFF_C)
      setFan(false);
  }

  bool linuxAlive = millis() - lastLinuxCmdMs < WATCHDOG_MS;
  if (linuxAlive)
  {
    digitalWrite(PIN_LED_FEEDER, ledFeeder);
    digitalWrite(PIN_LED_WIFI, ledWifi);
  }
  else
  {
    // backend is down: blink both connection LEDs instead of lying
    bool phase = (millis() / 500) % 2;
    digitalWrite(PIN_LED_FEEDER, phase);
    digitalWrite(PIN_LED_WIFI, phase);
  }

  delay(100);
}
