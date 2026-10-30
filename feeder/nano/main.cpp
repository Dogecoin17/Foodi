// Foodi feeder firmware – Arduino Nano (video prototype fallback).
// Same protocol as docs/ble-protocol.md, but carried over USB serial
// (115200 8N1) with framing: 0xAA 0x55 | len u8 | packet | crc8(packet, poly 0x07).
// The laptop CCM runs the brain; the Nano owns all feeder operations:
// schedule, idempotent dispense, hopper tracking, telemetry.
//
// Hardware: 28BYJ-48 stepper via ULN2003 on D4-D7 (D0/D1 are the USB serial
// link - do not use). No load cell: the CCM reads a kitchen scale via camera.
// Debug: sending a lone ASCII 'r' while no frame is in flight refills the hopper.
#include <Arduino.h>
#include <EEPROM.h>

// ---- pins ------------------------------------------------------------------
constexpr int PIN_IN1 = 4;
constexpr int PIN_IN2 = 5;
constexpr int PIN_IN3 = 6;
constexpr int PIN_IN4 = 7;
constexpr float STEPS_PER_GRAM = 41.0f; // TODO: calibrate - count steps for a known dispensed mass
constexpr uint32_t STEP_PERIOD_MS = 2;  // half-step rate ~500 steps/s

// ---- hard safety limits ------------------------------------------------------
constexpr uint16_t MAX_PORTION_G = 200;
constexpr uint32_t DISPENSE_TIMEOUT_MS = 20000; // jam / empty hopper guard
constexpr uint32_t TELEMETRY_PERIOD_MS = 2000;
constexpr uint16_t HOPPER_CAPACITY_G = 1000;
constexpr uint8_t LOW_FOOD_PCT = 15;

// ---- protocol constants (mirror ccm/app/protocol.py) -------------------------
constexpr uint8_t PROTO_VERSION = 1;
constexpr size_t HEADER_SIZE = 4; // version u8, type u8, seq u16 LE
constexpr uint8_t SYNC0 = 0xAA, SYNC1 = 0x55;
constexpr size_t MAX_PACKET = 64; // largest legal packet: SET_SCHEDULE with 8 entries = 45

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

// ---- little-endian helpers -----------------------------------------------------
static uint16_t rd16(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)rd16(p) | ((uint32_t)rd16(p + 2) << 16); }
static void wr16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }
static void wr32(uint8_t *p, uint32_t v) { wr16(p, v & 0xFFFF); wr16(p + 2, v >> 16); }

// ---- serial framing -------------------------------------------------------------
static uint8_t crc8(const uint8_t *data, size_t len)
{
  uint8_t crc = 0;
  while (len--)
  {
    crc ^= *data++;
    for (int i = 0; i < 8; i++)
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
  }
  return crc;
}

static void sendFrame(MsgType type, uint16_t seq, const uint8_t *body, size_t bodyLen)
{
  uint8_t pkt[HEADER_SIZE + 8];
  if (bodyLen > sizeof(pkt) - HEADER_SIZE)
    return;
  pkt[0] = PROTO_VERSION;
  pkt[1] = (uint8_t)type;
  wr16(pkt + 2, seq);
  memcpy(pkt + HEADER_SIZE, body, bodyLen);
  size_t len = HEADER_SIZE + bodyLen;
  Serial.write(SYNC0);
  Serial.write(SYNC1);
  Serial.write((uint8_t)len);
  Serial.write(pkt, len);
  Serial.write(crc8(pkt, len));
}

static void sendAck(uint16_t seq, uint32_t cmdId)
{
  uint8_t b[4];
  wr32(b, cmdId);
  sendFrame(MsgType::EVT_ACK, seq, b, sizeof(b));
}

static void sendNack(uint16_t seq, uint32_t cmdId, ErrorCode err)
{
  uint8_t b[5];
  wr32(b, cmdId);
  b[4] = (uint8_t)err;
  sendFrame(MsgType::EVT_NACK, seq, b, sizeof(b));
}

static void sendDispensed(uint16_t seq, uint32_t cmdId, uint16_t targetG, uint16_t actualG)
{
  uint8_t b[8];
  wr32(b, cmdId);
  wr16(b + 4, targetG);
  wr16(b + 6, actualG);
  sendFrame(MsgType::EVT_DISPENSED, seq, b, sizeof(b));
}

// Frame parser state machine: hunt sync -> len -> payload -> crc.
uint8_t inBuf[MAX_PACKET + 1];
size_t inLen = 0;
uint8_t inWant = 0;  // expected payload length once known
uint8_t syncSeen = 0;

// ---- idempotency: remember the last N dispense results --------------------------
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

// ---- EEPROM persistence ------------------------------------------------------------
// layout: 0 magic | 1..4 hopper float | 5..8 sched counter u32 | 9 sched count | 10.. entries
constexpr uint8_t EEPROM_MAGIC = 0xF1;
constexpr int ADDR_MAGIC = 0, ADDR_HOPPER = 1, ADDR_SCHED_CTR = 5, ADDR_SCHED_N = 9, ADDR_SCHED = 10;

float hopperRemainingG = HOPPER_CAPACITY_G;

uint8_t foodLevelPct()
{
  float pct = 100.0f * hopperRemainingG / HOPPER_CAPACITY_G;
  return pct < 0 ? 0 : (uint8_t)pct;
}

// ---- schedule ----------------------------------------------------------------------
constexpr size_t MAX_SCHEDULE = 8;
struct ScheduleEntry
{
  uint16_t minuteOfDay;
  uint16_t grams;
  uint8_t daysMask; // bit0 = Monday
};
ScheduleEntry schedule[MAX_SCHEDULE] = {};
size_t scheduleCount = 0;
uint32_t schedCmdCounter = 0; // ids are 0x80000000 | counter

void saveSchedule()
{
  EEPROM.update(ADDR_SCHED_N, (uint8_t)scheduleCount);
  for (size_t i = 0; i < scheduleCount; i++)
    EEPROM.put(ADDR_SCHED + i * sizeof(ScheduleEntry), schedule[i]);
}

void loadPersistent()
{
  if (EEPROM.read(ADDR_MAGIC) != EEPROM_MAGIC)
  {
    EEPROM.update(ADDR_MAGIC, EEPROM_MAGIC); // first boot: defaults already set
    EEPROM.put(ADDR_HOPPER, hopperRemainingG);
    return;
  }
  EEPROM.get(ADDR_HOPPER, hopperRemainingG);
  EEPROM.get(ADDR_SCHED_CTR, schedCmdCounter);
  scheduleCount = EEPROM.read(ADDR_SCHED_N);
  if (scheduleCount > MAX_SCHEDULE)
    scheduleCount = MAX_SCHEDULE;
  for (size_t i = 0; i < scheduleCount; i++)
    EEPROM.get(ADDR_SCHED + i * sizeof(ScheduleEntry), schedule[i]);
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

// ---- dispense -----------------------------------------------------------------------
struct Dispense
{
  uint32_t cmdId;
  uint16_t target;
  uint32_t startedMs;
  bool active;
  uint32_t stepsTotal;
  uint32_t stepsRemaining;
  uint32_t nextStepMs;
};
Dispense job{0, 0, 0, false, 0, 0, 0};

// 28BYJ-48 half-step sequence (8 phases) on IN1..IN4
const uint8_t STEP_SEQ[8][4] = {
    {1, 0, 0, 0}, {1, 1, 0, 0}, {0, 1, 0, 0}, {0, 1, 1, 0},
    {0, 0, 1, 0}, {0, 0, 1, 1}, {0, 0, 0, 1}, {1, 0, 0, 1}};
uint8_t stepPhase = 0;

void stepOnce()
{
  digitalWrite(PIN_IN1, STEP_SEQ[stepPhase][0]);
  digitalWrite(PIN_IN2, STEP_SEQ[stepPhase][1]);
  digitalWrite(PIN_IN3, STEP_SEQ[stepPhase][2]);
  digitalWrite(PIN_IN4, STEP_SEQ[stepPhase][3]);
  stepPhase = (stepPhase + 1) & 7;
}

void motorOff()
{
  digitalWrite(PIN_IN1, LOW);
  digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW);
  digitalWrite(PIN_IN4, LOW); // coils off: no idle heating, free to turn
}

float deliveredGrams() { return (job.stepsTotal - job.stepsRemaining) / STEPS_PER_GRAM; }

void finishDispense(bool ok, ErrorCode err, uint16_t seq)
{
  motorOff();
  uint16_t actual = (uint16_t)(deliveredGrams() + 0.5f);
  job.active = false;

  if (ok)
  {
    hopperRemainingG -= actual;
    EEPROM.put(ADDR_HOPPER, hopperRemainingG);
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
  job.cmdId = cmdId;
  job.target = grams;
  job.startedMs = millis();
  job.active = true;
  job.stepsTotal = job.stepsRemaining = (uint32_t)(grams * STEPS_PER_GRAM + 0.5f);
  job.nextStepMs = millis();
  state = State::Dispensing;
}

void updateDispense()
{
  if (!job.active)
    return;
  if ((int32_t)(millis() - job.nextStepMs) >= 0)
  {
    job.nextStepMs = millis() + STEP_PERIOD_MS;
    stepOnce();
    if (--job.stepsRemaining == 0)
    {
      finishDispense(true, ErrorCode::Jam, 0);
      return;
    }
  }
  if (millis() - job.startedMs > DISPENSE_TIMEOUT_MS)
    finishDispense(false, ErrorCode::Jam, 0); // could not finish in time
}

// ---- scheduled meals ----------------------------------------------------------------
int32_t lastFiredMinute = -1;

void checkSchedule()
{
  if (!timeValid || job.active)
    return;
  uint16_t minuteOfDay;
  uint8_t dayOfWeek;
  localTime(minuteOfDay, dayOfWeek);
  int32_t minuteKey = (int32_t)(unixNow() / 60); // unique per minute, avoids double-fire
  if (minuteKey == lastFiredMinute)
    return;
  for (size_t i = 0; i < scheduleCount; i++)
  {
    const ScheduleEntry &e = schedule[i];
    if (e.minuteOfDay == minuteOfDay && (e.daysMask & (1 << dayOfWeek)))
    {
      lastFiredMinute = minuteKey;
      schedCmdCounter = (schedCmdCounter + 1) & 0x7FFFFFFF;
      EEPROM.put(ADDR_SCHED_CTR, schedCmdCounter);
      startDispense(0, 0x80000000u | schedCmdCounter, e.grams);
      return; // one meal per minute is enough
    }
  }
}

// ---- command handling ----------------------------------------------------------------
void handlePacket(const uint8_t *data, size_t len)
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
      sendNack(seq, 0, ErrorCode::Busy);
    else
      sendAck(seq, 0); // no load cell: tare is a no-op - still ACK
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

// Feed one serial byte into the frame parser. Returns true while inside a frame.
bool feedParser(uint8_t b)
{
  if (syncSeen == 0)
  {
    if (b == SYNC0)
      syncSeen = 1;
    return false;
  }
  if (syncSeen == 1)
  {
    if (b == SYNC1)
    {
      syncSeen = 2;
      inLen = 0;
      inWant = 0;
    }
    else
    {
      syncSeen = (b == SYNC0) ? 1 : 0;
    }
    return true;
  }
  if (inWant == 0)
  {
    if (b == 0 || b > MAX_PACKET)
    {
      syncSeen = 0; // implausible length: resync
      return false;
    }
    inWant = b;
    return true;
  }
  inBuf[inLen++] = b;
  if (inLen < (size_t)inWant + 1) // +1 for the CRC byte
    return true;
  syncSeen = 0;
  inLen = 0;
  if (crc8(inBuf, inWant) == inBuf[inWant])
    handlePacket(inBuf, inWant);
  return false;
}

// ---- telemetry ------------------------------------------------------------------------
uint32_t lastTelemetryMs = 0;

void sendTelemetry()
{
  uint8_t b[6];
  wr32(b, 0); // weight_g: no load cell - the CCM reads the scale via camera
  b[4] = foodLevelPct();
  b[5] = (uint8_t)state;
  sendFrame(MsgType::EVT_TELEMETRY, 0, b, sizeof(b));
}

void setup()
{
  Serial.begin(115200);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  motorOff(); // motor must be OFF at boot and after any fault
  loadPersistent();
}

void loop()
{
  while (Serial.available())
  {
    uint8_t b = (uint8_t)Serial.read();
    bool inFrame = feedParser(b);
    if (!inFrame && b == 'r') // debug shortcut: refill hopper from a serial monitor
    {
      hopperRemainingG = HOPPER_CAPACITY_G;
      EEPROM.put(ADDR_HOPPER, hopperRemainingG);
      if (state == State::LowFood)
        state = State::Idle;
    }
  }
  updateDispense();
  checkSchedule();
  if (millis() - lastTelemetryMs >= TELEMETRY_PERIOD_MS)
  {
    lastTelemetryMs = millis();
    sendTelemetry();
  }
}
