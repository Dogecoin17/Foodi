# Foodi – Setting Up at Home

This guide takes you from unboxing to your pet's first scheduled meal. It
takes about 20 minutes. You will need your home Wi-Fi password and a
smartphone.

## In the box

- **CCM** (central computing module) – the brain
- **Feeder** – food hopper, bowl, camera and scale plate
- 12.6 V charging adapter (works for both units)
- This guide

Both units run from their internal batteries or plugged into the wall.
Batteries charge whenever a unit is plugged in.

## 1. Choose the spot

- Put the **feeder** on a flat, stable surface where your pet eats, within
  range of your Wi-Fi. Keep it away from water bowls and direct sunlight
  (glare makes the display harder for the camera to read).
- Put the **CCM** anywhere with good Wi-Fi – it does not need to be next to
  the feeder. The two find each other on their own.
- Place the bowl on the scale plate with the scale's display facing the
  feeder's camera. The camera watches your pet eat and reads the weight off
  the display – that is how Foodi knows how much was eaten.

## 2. Power on

1. Flip the power switch on each unit (or plug them in).
2. Check the CCM's lights:

| Light | Meaning |
|---|---|
| Power | On whenever the unit has power (battery or wall) |
| On | The computer inside is running – takes up to a minute after switching on |
| Wi-Fi | Lit when the CCM is on your home network |
| Bluetooth | Lit when the CCM is linked to a feeder |
| Charging | Lit while the wall adapter is connected |

If the CCM feels warm, its fans turn on by themselves – that is normal.

## 3. Connect the CCM to your Wi-Fi (one time)

1. Connect the CCM to a computer with a USB-C cable.
2. Open **Arduino App Lab** on the computer; the CCM appears automatically.
3. Follow the first-time setup: choose a password for the CCM, then select
   your **home Wi-Fi network** and enter its password.
4. Unplug the USB cable. The **Wi-Fi light** comes on within a minute – the
   CCM now remembers your network and joins it on every power-up.

> Your Wi-Fi must be a 2.4 GHz or combined network – the feeder cannot see
> 5 GHz-only networks.

## 4. Pair the feeder

1. Switch the feeder on near the CCM.
2. Nothing else to press: the CCM finds the feeder by name, links to it, and
   hands it your Wi-Fi details so its camera can send video. The **Bluetooth
   light** on the CCM turns on when the link is up, and the feeder joins your
   Wi-Fi a few seconds later.
3. From now on the pair reconnects automatically, even after power cuts. The
   feeder keeps mealtimes on its own clock, so a Wi-Fi outage never means a
   missed meal.

## 5. Put the app on your phone

1. Connect your phone to the **same Wi-Fi** as the CCM.
2. Open the browser and go to **`http://<ccm-address>:8000`** – the CCM's
   address is shown in Arduino App Lab (or your router's device list).
3. When the dashboard loads, use your browser's **Add to Home Screen** option.
   Foodi now sits on your home screen like any other app.

## 6. Fill it up and feed

1. Open the hopper lid and fill with **dry kibble only** (max 1 kg – the app
   warns you at 15 % remaining). Wet food and treats jam the dispenser.
2. Put the empty bowl on the scale plate.
3. In the app, set your pet's **profile** (species, weight, age) – Foodi's AI
   uses it, together with what your pet actually eats, to recommend portion
   sizes and flag unusual eating patterns.
4. Press **Feed now** for a test portion. Watch the bowl weight climb on the
   dashboard and check the live camera view.
5. Set the **schedule** in the app (times, portions, days). Done – Foodi feeds
   on time, records every meal, and the dashboard shows daily totals, trends
   and alerts.

## Everyday life with Foodi

- **Refill** when the low-food alert appears. Open the hopper, top up, then
  press **Refill done** in the app so the food-level counter starts again
  from 100 %.
- **Power cuts / Wi-Fi drops:** the feeder runs its schedule from its own
  memory and reports what it dispensed once the link returns.
- **Moving house or new Wi-Fi:** repeat step 3, then power-cycle the feeder so
  it picks up the new network from the CCM.

## If something's wrong

| Symptom | What to do |
|---|---|
| Wi-Fi light off | Repeat step 3; check the password; keep the CCM away from thick walls |
| Bluetooth light off | Power-cycle the feeder near the CCM; pairing is automatic |
| No video in the app | Check the feeder and phone are on the same Wi-Fi; power-cycle the feeder |
| Feeder did not dispense | Check the hopper is not empty and the chute is not jammed; clear, then press Feed now |
| Weight looks wrong | Make sure the scale display faces the camera and has no glare; re-seat the bowl |
| Fans running constantly | Normal under load; if the case is hot to the touch, move the CCM somewhere ventilated |

## Safety notes

- Charge only with the supplied 12.6 V adapter.
- Do not open the battery compartments; the cells are not user-replaceable.
- Dry kibble only; keep the hopper dry and clean it monthly with a dry cloth.
- Foodi supports your pet's diet but does not replace a vet – follow your
  vet's advice over any recommendation in the app.
