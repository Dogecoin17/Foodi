# Foodi BLE protocol v1 (CCM <-> Feeder)

Roles: **Feeder = peripheral (GATT server)**, **CCM = central (client)**. All integers little-endian.

## GATT
| Characteristic | UUID (placeholder – generate your own) | Props | Purpose |
|---|---|---|---|
| Service | `f00d0000-0000-4000-8000-00805f9b34fb` | – | Foodi feeder service |
| COMMAND | `f00d0001-0000-4000-8000-00805f9b34fb` | write | CCM -> feeder commands |
| EVENT | `f00d0002-0000-4000-8000-00805f9b34fb` | notify | feeder -> CCM ACK/NACK/DISPENSED |
| TELEMETRY | `f00d0003-0000-4000-8000-00805f9b34fb` | notify (every 2 s) | weight, food level, state |

Negotiate MTU >= 64. Every message fits in one packet.

## Header (4 bytes)
| Byte | Field |
|---|---|
| 0 | version (=1) |
| 1 | message type |
| 2–3 | sequence number (u16) |

## Commands (CCM -> feeder)
| Type | Name | Payload |
|---|---|---|
| 0x01 | DISPENSE | `cmd_id u32`, `grams u16` |
| 0x02 | CANCEL | `cmd_id u32` |
| 0x03 | TARE | – |
| 0x04 | SET_SCHEDULE | `count u8`, then per entry: `minute_of_day u16`, `grams u16`, `days_mask u8` (bit0 = Monday) |
| 0x05 | SYNC_TIME | `unix_ts u32`, `tz_offset_min i16` |

## Events (feeder -> CCM)
| Type | Name | Payload |
|---|---|---|
| 0x81 | ACK | `cmd_id u32` (0 if not applicable) |
| 0x82 | NACK | `cmd_id u32`, `error u8` |
| 0x83 | DISPENSED | `cmd_id u32`, `target_g u16`, `actual_g u16` |
| 0x84 | TELEMETRY | `weight_g i32`, `food_level_pct u8`, `state u8` |

State: 0 idle, 1 dispensing, 2 error, 3 low food.
Errors: 1 bad version, 2 bad payload, 3 busy, 4 empty hopper, 5 over limit, 6 jam.

## Rules
1. **Idempotency:** the feeder remembers the last N `cmd_id`s; a repeated `DISPENSE` with a known id returns the original result and does **not** dispense again.
2. **Scheduled meals** use ids with the top bit set (`0x80000000 | counter`), manual ones do not.
3. **Autonomy:** the feeder executes its stored schedule with or without a connection, and reports meals it dispensed while disconnected on reconnect.
4. **Sync on connect:** CCM sends SYNC_TIME then SET_SCHEDULE after every (re)connect.
5. **Limits:** feeder rejects portions above its own `MAX_PORTION_G` with NACK `over limit`, whatever the CCM says.
6. **Timeouts:** CCM waits 2 s for ACK, retries up to 3 times with the same `cmd_id`, then raises an alert.
