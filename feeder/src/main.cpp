// Foodi feeder firmware – SKELETON. Follows docs/ble-protocol.md (v1). Not tested on hardware.
#include <Arduino.h>
#include <HX711.h>
// #include <NimBLEDevice.h>   // Phase 2: BLE peripheral

// ---- pins: adjust to the real wiring --------------------------------------
constexpr int PIN_HX711_DOUT = 4;
constexpr int PIN_HX711_SCK  = 5;
constexpr int PIN_MOTOR_PWM  = 6;   // auger motor driver

// ---- hard safety limits (enforced here regardless of what the CCM sends) ---
constexpr uint16_t MAX_PORTION_G      = 200;
constexpr uint32_t DISPENSE_TIMEOUT_MS = 20000;  // jam / empty hopper guard

enum class State : uint8_t { Idle = 0, Dispensing = 1, Error = 2, LowFood = 3 };
State state = State::Idle;

HX711 scale;
float calibrationFactor = 1.0f;  // TODO: calibrate with a known mass

struct Dispense { uint32_t cmdId; uint16_t target; float startWeight; uint32_t startedMs; bool active; };
Dispense job{0, 0, 0, 0, false};

void motorOff() { analogWrite(PIN_MOTOR_PWM, 0); }

float bowlGrams() { return scale.get_units(3); }

void startDispense(uint32_t cmdId, uint16_t grams) {
  if (grams > MAX_PORTION_G) { /* TODO: send NACK(over limit) */ return; }
  // TODO: if cmdId already seen (ring buffer of last N ids) -> resend stored result, do NOT dispense
  job = {cmdId, grams, bowlGrams(), millis(), true};
  state = State::Dispensing;
  analogWrite(PIN_MOTOR_PWM, 200);
}

void updateDispense() {
  if (!job.active) return;
  float delivered = bowlGrams() - job.startWeight;
  bool done = delivered >= job.target;
  bool timeout = millis() - job.startedMs > DISPENSE_TIMEOUT_MS;
  if (done || timeout) {
    motorOff();
    job.active = false;
    state = timeout && !done ? State::Error : State::Idle;
    // TODO: notify DISPENSED(cmdId, target, actual = delivered) or NACK(JAM)
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_MOTOR_PWM, OUTPUT);
  motorOff();  // motor must be OFF at boot and after any fault
  scale.begin(PIN_HX711_DOUT, PIN_HX711_SCK);
  scale.set_scale(calibrationFactor);
  scale.tare();
  // TODO Phase 2: NimBLE service + characteristics (COMMAND write, EVENT/TELEMETRY notify)
  // TODO Phase 2: load schedule from NVS, run it from local time even when disconnected
  // TODO Phase 2: Wi-Fi + MJPEG camera task (separate from the BLE control path)
}

void loop() {
  updateDispense();
  // TODO: every 2 s notify TELEMETRY(weight, food level, state)
  // TODO: check stored schedule against RTC time
  delay(20);
}
