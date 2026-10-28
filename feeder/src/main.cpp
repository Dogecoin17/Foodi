// Foodi feeder firmware – ESP32-S3. Implements docs/ble-protocol.md (v1).
// Roles: feeder = BLE peripheral (GATT server), CCM = central (client).
#include <Arduino.h>
#include <Preferences.h>
#include <HX711.h>
#include <NimBLEDevice.h>

// ---- pins: adjust to the real wiring --------------------------------------
constexpr int PIN_HX711_DOUT = 4;
constexpr int PIN_HX711_SCK = 5;
constexpr int PIN_MOTOR_PWM = 6; // auger motor driver

// ---- hard safety limits (enforced here regardless of what the CCM sends) ---
constexpr uint16_t MAX_PORTION_G = 200;
constexpr uint32_t DISPENSE_TIMEOUT_MS = 20000; // jam / empty hopper guard
constexpr uint32_t TELEMETRY_PERIOD_MS = 2000;
constexpr uint16_t HOPPER_CAPACITY_G = 1000;
constexpr uint8_t LOW_FOOD_PCT = 15;

// ---- dispense tuning -------------------------------------------------------
constexpr int MOTOR_PWM_FAST = 220;
constexpr int MOTOR_PWM_SLOW = 140;
constexpr float COARSE_MARGIN_G = 10.0f; // switch fast->slow this far from target

// ---- protocol constants (mirror ccm/app/protocol.py) ------------------------
constexpr uint8_t PROTO_VERSION = 1;
constexpr size_t HEADER_SIZE = 4; // version u8, type u8, seq u16 LE

enum class MsgType : uint8_t
{
  CMD_DISPENSE = 0x01,
  CMD_CANCEL = 0x02,
  CMD_TARE = 0x03,
  CMD_SET_SCHEDULE = 0x04,
  CMD_SYNC_TIME = 0x05,
  EVT_ACK = 0x81,
  EVT_NACK = 0x82,
  EVT_DISPENSED = 0x83,
  EVT_TELEMETRY = 0x84,
};

enum class ErrorCode : uint8_t
{
  BadVersion = 1,
  BadPayload = 2,
  Busy = 3,
  EmptyHopper = 4,
  OverLimit = 5,
  Jam = 6,
};

enum class State : uint8_t
{
  Idle = 0,
  Dispensing = 1,
  Error = 2,
  LowFood = 3
};
State state = State::Idle;

// ---- BLE UUIDs (docs/ble-protocol.md) ---------------------------------------
static const char *SVC_UUID = "f00d0000-0000-4000-8000-00805f9b34fb";
static const char *CHR_COMMAND = "f00d0001-0000-4000-8000-00805f9b34fb";
static const char *CHR_EVENT = "f00d0002-0000-4000-8000-00805f9b34fb";
static const char *CHR_TELEMETRY = "f00d0003-0000-4000-8000-00805f9b34fb";

NimBLECharacteristic *chrEvent = nullptr;
NimBLECharacteristic *chrTelemetry = nullptr;
bool ccmConnected = false;

// ---- little-endian helpers ---------------------------------------------------
static uint16_t rd16(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)rd16(p) | ((uint32_t)rd16(p + 2) << 16); }
static void wr16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }
static void wr32(uint8_t *p, uint32_t v) { wr16(p, v & 0xFFFF); wr16(p + 2, v >> 16); }

// ---- events ------------------------------------------------------------------
static void sendPacket(NimBLECharacteristic *chr, MsgType type, uint16_t seq,
                       const uint8_t *body, size_t bodyLen)
{
  if (!chr || !ccmConnected)
    return;
  uint8_t buf[HEADER_SIZE + 16];
  if (bodyLen > sizeof(buf) - HEADER_SIZE)
    return;
  buf[0] = PROTO_VERSION;
  buf[1] = (uint8_t)type;
  wr16(buf + 2, seq);
  memcpy(buf + HEADER_SIZE, body, bodyLen);
  chr->setValue(buf, HEADER_SIZE + bodyLen);
  chr->notify();
}

static void sendAck(uint16_t seq, uint32_t cmdId)
{
  uint8_t b[4];
  wr32(b, cmdId);
  sendPacket(chrEvent, MsgType::EVT_ACK, seq, b, sizeof(b));
}

static void sendNack(uint16_t seq, uint32_t cmdId, ErrorCode err)
{
  uint8_t b[5];
  wr32(b, cmdId);
  b[4] = (uint8_t)err;
  sendPacket(chrEvent, MsgType::EVT_NACK, seq, b, sizeof(b));
}

// ---- idempotency: remember the last N dispense results ------------------------
struct CmdResult
{
  uint32_t cmdId;
  uint16_t targetG;
  uint16_t actualG;
  bool ok;
};
constexpr size_t CMD_CACHE = 8;
CmdResult cmdCache[CMD_CACHE] = {};
size_t cmdCacheNext = 0;

static const CmdResult *findCmd(uint32_t cmdId)
{
  for (size_t i = 0; i < CMD_CACHE; i++)
    if (cmdCache[i].cmdId == cmdId)
      return &cmdCache[i];
  return nullptr;
}

static void rememberCmd(const CmdResult &r)
{
  cmdCache[cmdCacheNext] = r;
  cmdCacheNext = (cmdCacheNext + 1) % CMD_CACHE;
}

// ---- missed-meal reports: queue DISPENSED events sent while disconnected -------
struct PendingReport
{
  uint32_t cmdId;
  uint16_t targetG;
  uint16_t actualG;
};
constexpr size_t REPORT_QUEUE = 8;
PendingReport reports[REPORT_QUEUE] = {};
size_t reportCount = 0;

static void sendDispensed(uint16_t seq, uint32_t cmdId, uint16_t targetG, uint16_t actualG)
{
  uint8_t b[8];
  wr32(b, cmdId);
  wr16(b + 4, targetG);
  wr16(b + 6, actualG);
  if (ccmConnected)
  {
    sendPacket(chrEvent, MsgType::EVT_DISPENSED, seq, b, sizeof(b));
  }
  else if (reportCount < REPORT_QUEUE)
  {
    reports[reportCount++] = {cmdId, targetG, actualG}; // delivered on reconnect
  }
}

static void flushReports()
{
  while (reportCount > 0 && ccmConnected)
  {
    reportCount--;
    sendDispensed(0, reports[reportCount].cmdId, reports[reportCount].targetG,
                  reports[reportCount].actualG);
    delay(20);
  }
}

// ---- load cell ------------------------------------------------------------------
HX711 scale;
float calibrationFactor = 420.0f; // TODO: calibrate with a known mass
float filteredGrams = 0.0f;

float bowlGrams()
{
  // Exponential filter over raw readings; called from loop() when HX711 is ready.
  if (scale.is_ready())
  {
    float g = scale.get_units(1);
    filteredGrams += 0.3f * (g - filteredGrams);
  }
  return filteredGrams;
}

// ---- hopper level (estimated, persisted) -----------------------------------------
Preferences prefs;
float hopperRemainingG = HOPPER_CAPACITY_G;

uint8_t foodLevelPct()
{
  float pct = 100.0f * hopperRemainingG / HOPPER_CAPACITY_G;
  if (pct < 0)
    pct = 0;
  return (uint8_t)pct;
}

void saveHopper()
{
  prefs.putFloat("hopper_g", hopperRemainingG);
}

// ---- schedule -----------------------------------------------------------------------
constexpr size_t MAX_SCHEDULE = 8;
struct ScheduleEntry
{
  uint16_t minuteOfDay;
  uint16_t grams;
  uint8_t daysMask; // bit0 = Monday
};
ScheduleEntry schedule[MAX_SCHEDULE] = {};
size_t scheduleCount = 0;

void saveSchedule()
{
  prefs.putUChar("sched_n", (uint8_t)scheduleCount);
  prefs.putBytes("sched", schedule, scheduleCount * sizeof(ScheduleEntry));
}

void loadSchedule()
{
  scheduleCount = prefs.getUChar("sched_n", 0);
  if (scheduleCount > MAX_SCHEDULE)
    scheduleCount = MAX_SCHEDULE;
  prefs.getBytes("sched", schedule, scheduleCount * sizeof(ScheduleEntry));
}

// ---- time (set by SYNC_TIME, runs autonomously afterwards) ----------------------------
bool timeValid = false;
uint32_t baseUnixTs = 0;
int16_t tzOffsetMin = 0;
uint32_t baseMillis = 0;

uint32_t unixNow() { return baseUnixTs + (millis() - baseMillis) / 1000; }

void localTime(uint16_t &minuteOfDay, uint8_t &dayOfWeek) // dayOfWeek: 0 = Monday
{
  uint32_t local = unixNow() + (int32_t)tzOffsetMin * 60;
  uint32_t days = local / 86400;
  minuteOfDay = (uint16_t)((local % 86400) / 60);
  dayOfWeek = (uint8_t)((days + 3) % 7); // 1970-01-01 was a Thursday (3 if Mon=0)
}

// ---- dispense --------------------------------------------------------------------------
struct Dispense
{
  uint32_t cmdId;
  uint16_t target;
  float startWeight;
  uint32_t startedMs;
  bool active;
};
Dispense job{0, 0, 0, 0, false};

void motorOff() { analogWrite(PIN_MOTOR_PWM, 0); }

void finishDispense(bool ok, ErrorCode err, uint16_t seq)
{
  motorOff();
  float delivered = bowlGrams() - job.startWeight;
  if (delivered < 0)
    delivered = 0;
  uint16_t actual = (uint16_t)(delivered + 0.5f);
  job.active = false;

  if (ok)
  {
    hopperRemainingG -= actual;
    saveHopper();
    state = foodLevelPct() < LOW_FOOD_PCT ? State::LowFood : State::Idle;
    rememberCmd({job.cmdId, job.target, actual, true});
    sendDispensed(seq, job.cmdId, job.target, actual);
  }
  else
  {
    state = State::Error;
    rememberCmd({job.cmdId, job.target, actual, false});
    sendNack(seq, job.cmdId, err);
  }
}

void startDispense(uint16_t seq, uint32_t cmdId, uint16_t grams)
{
  if (grams > MAX_PORTION_G)
  {
    sendNack(seq, cmdId, ErrorCode::OverLimit);
    return;
  }
  if (job.active)
  {
    sendNack(seq, cmdId, ErrorCode::Busy);
    return;
  }
  if (foodLevelPct() == 0 || hopperRemainingG < grams)
  {
    sendNack(seq, cmdId, ErrorCode::EmptyHopper);
    return;
  }
  const CmdResult *seen = findCmd(cmdId);
  if (seen)
  {
    // Repeated command id: replay the stored result, do NOT dispense again.
    if (seen->ok)
      sendDispensed(seq, cmdId, seen->targetG, seen->actualG);
    else
      sendNack(seq, cmdId, ErrorCode::Jam);
    return;
  }
  sendAck(seq, cmdId);
  job = {cmdId, grams, bowlGrams(), millis(), true};
  state = State::Dispensing;
  analogWrite(PIN_MOTOR_PWM, MOTOR_PWM_FAST);
}

void updateDispense()
{
  if (!job.active)
    return;
  float delivered = bowlGrams() - job.startWeight;
  if (delivered >= job.target)
  {
    finishDispense(true, ErrorCode::Jam, 0);
    return;
  }
  if (millis() - job.startedMs > DISPENSE_TIMEOUT_MS)
  {
    finishDispense(false, ErrorCode::Jam, 0);
    return;
  }
  analogWrite(PIN_MOTOR_PWM, delivered >= job.target - COARSE_MARGIN_G ? MOTOR_PWM_SLOW
                                                                       : MOTOR_PWM_FAST);
}

// ---- scheduled meals -----------------------------------------------------------------------
uint32_t schedCmdCounter = 0; // persisted; ids are 0x80000000 | counter
int lastFiredMinute = -1;

void checkSchedule()
{
  if (!timeValid || job.active)
    return;
  uint16_t minuteOfDay;
  uint8_t dayOfWeek;
  localTime(minuteOfDay, dayOfWeek);
  int minuteKey = (int)(unixNow() / 60); // unique per minute, avoids double-fire
  if (minuteKey == lastFiredMinute)
    return;
  for (size_t i = 0; i < scheduleCount; i++)
  {
    const ScheduleEntry &e = schedule[i];
    if (e.minuteOfDay == minuteOfDay && (e.daysMask & (1 << dayOfWeek)))
    {
      lastFiredMinute = minuteKey;
      schedCmdCounter = (schedCmdCounter + 1) & 0x7FFFFFFF;
      prefs.putUInt("sched_ctr", schedCmdCounter);
      startDispense(0, 0x80000000u | schedCmdCounter, e.grams);
      return; // one meal per minute is enough
    }
  }
}

// ---- command handling -------------------------------------------------------------------------
void handleCommand(const uint8_t *data, size_t len)
{
  if (len < HEADER_SIZE)
    return;
  uint8_t version = data[0];
  MsgType type = (MsgType)data[1];
  uint16_t seq = rd16(data + 2);
  const uint8_t *body = data + HEADER_SIZE;
  size_t bodyLen = len - HEADER_SIZE;

  if (version != PROTO_VERSION)
  {
    sendNack(seq, 0, ErrorCode::BadVersion);
    return;
  }

  switch (type)
  {
  case MsgType::CMD_DISPENSE:
    if (bodyLen != 6)
      sendNack(seq, 0, ErrorCode::BadPayload);
    else
      startDispense(seq, rd32(body), rd16(body + 4));
    break;

  case MsgType::CMD_CANCEL:
    if (bodyLen != 4)
    {
      sendNack(seq, 0, ErrorCode::BadPayload);
    }
    else if (job.active && job.cmdId == rd32(body))
    {
      sendAck(seq, job.cmdId);
      finishDispense(true, ErrorCode::Jam, 0); // report partial amount delivered
    }
    else
    {
      sendAck(seq, rd32(body)); // nothing running; idempotent no-op
    }
    break;

  case MsgType::CMD_TARE:
    if (job.active)
    {
      sendNack(seq, 0, ErrorCode::Busy);
    }
    else
    {
      scale.tare();
      filteredGrams = 0.0f;
      sendAck(seq, 0);
    }
    break;

  case MsgType::CMD_SYNC_TIME:
    if (bodyLen != 6)
    {
      sendNack(seq, 0, ErrorCode::BadPayload);
    }
    else
    {
      baseUnixTs = rd32(body);
      tzOffsetMin = (int16_t)rd16(body + 4);
      baseMillis = millis();
      timeValid = true;
      sendAck(seq, 0);
    }
    break;

  case MsgType::CMD_SET_SCHEDULE:
  {
    if (bodyLen < 1)
    {
      sendNack(seq, 0, ErrorCode::BadPayload);
      break;
    }
    uint8_t count = body[0];
    if (bodyLen != (size_t)(1 + count * 5) || count > MAX_SCHEDULE)
    {
      sendNack(seq, 0, ErrorCode::BadPayload);
      break;
    }
    scheduleCount = count;
    for (size_t i = 0; i < count; i++)
    {
      const uint8_t *e = body + 1 + i * 5;
      schedule[i] = {rd16(e), rd16(e + 2), e[4]};
      if (schedule[i].grams > MAX_PORTION_G)
        schedule[i].grams = MAX_PORTION_G; // clamp, never trust the sender
    }
    saveSchedule();
    sendAck(seq, 0);
    break;
  }

  default:
    sendNack(seq, 0, ErrorCode::BadPayload);
    break;
  }
}

// ---- BLE ---------------------------------------------------------------------------------------
class CmdCallbacks : public NimBLECharacteristicCallbacks
{
  void onWrite(NimBLECharacteristic *chr, NimBLEConnInfo &connInfo) override
  {
    NimBLEAttValue v = chr->getValue();
    handleCommand(v.data(), v.size());
  }
};

class ServerCallbacks : public NimBLEServerCallbacks
{
  void onConnect(NimBLEServer *server, NimBLEConnInfo &connInfo) override
  {
    ccmConnected = true;
    server->updateConnParams(connInfo.getConnHandle(), 12, 48, 0, 400);
  }
  void onDisconnect(NimBLEServer *server, NimBLEConnInfo &connInfo, int reason) override
  {
    ccmConnected = false;
    NimBLEDevice::startAdvertising();
  }
};

void setupBle()
{
  NimBLEDevice::init("foodi-feeder");
  NimBLEDevice::setMTU(128);
  NimBLEDevice::setPower(ESP_PWR_LVL_P9);
  NimBLEServer *server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  NimBLEService *svc = server->createService(SVC_UUID);
  NimBLECharacteristic *chrCmd = svc->createCharacteristic(CHR_COMMAND, NIMBLE_PROPERTY::WRITE);
  chrEvent = svc->createCharacteristic(CHR_EVENT, NIMBLE_PROPERTY::NOTIFY);
  chrTelemetry = svc->createCharacteristic(CHR_TELEMETRY, NIMBLE_PROPERTY::NOTIFY);
  chrCmd->setCallbacks(new CmdCallbacks());
  svc->start();

  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(SVC_UUID);
  adv->setName("foodi-feeder");
  adv->start();
}

// ---- telemetry ----------------------------------------------------------------------------------
uint32_t lastTelemetryMs = 0;

void sendTelemetry()
{
  uint8_t b[6];
  wr32(b, (uint32_t)(int32_t)(bowlGrams() + 0.5f)); // weight_g i32 LE
  b[4] = foodLevelPct();
  b[5] = (uint8_t)state;
  sendPacket(chrTelemetry, MsgType::EVT_TELEMETRY, 0, b, sizeof(b));
}

// ---- serial console (debug + maintenance) ----------------------------------------------------------
void handleSerial()
{
  if (!Serial.available())
    return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd == "refill")
  {
    hopperRemainingG = HOPPER_CAPACITY_G;
    saveHopper();
    if (state == State::LowFood)
      state = State::Idle;
    Serial.println("hopper refilled");
  }
  else if (cmd == "tare" && !job.active)
  {
    scale.tare();
    filteredGrams = 0.0f;
    Serial.println("tared");
  }
  else if (cmd.startsWith("cal ")) // "cal 155.5" = known mass in grams on the scale
  {
    float known = cmd.substring(4).toFloat();
    if (known > 0)
    {
      calibrationFactor = scale.get_units(10) / known;
      scale.set_scale(calibrationFactor);
      prefs.putFloat("cal", calibrationFactor);
      Serial.printf("calibrationFactor = %.2f (saved)\n", calibrationFactor);
    }
  }
  else if (cmd == "status")
  {
    Serial.printf("state=%d bowl=%.1fg hopper=%u%% sched=%u time=%s\n", (int)state,
                  bowlGrams(), foodLevelPct(), (unsigned)scheduleCount,
                  timeValid ? "ok" : "unset");
  }
}

void setup()
{
  Serial.begin(115200);
  pinMode(PIN_MOTOR_PWM, OUTPUT);
  motorOff(); // motor must be OFF at boot and after any fault

  prefs.begin("foodi", false);
  calibrationFactor = prefs.getFloat("cal", calibrationFactor);
  hopperRemainingG = prefs.getFloat("hopper_g", HOPPER_CAPACITY_G);
  schedCmdCounter = prefs.getUInt("sched_ctr", 0);
  loadSchedule();

  scale.begin(PIN_HX711_DOUT, PIN_HX711_SCK);
  scale.set_scale(calibrationFactor);
  scale.tare();

  setupBle();
  Serial.println("foodi-feeder up, advertising");
}

void loop()
{
  bowlGrams(); // keep the filter fed
  updateDispense();
  checkSchedule();
  handleSerial();

  if (ccmConnected)
  {
    if (reportCount > 0)
      flushReports();
    if (millis() - lastTelemetryMs >= TELEMETRY_PERIOD_MS)
    {
      lastTelemetryMs = millis();
      sendTelemetry();
    }
  }
  delay(10);
}
