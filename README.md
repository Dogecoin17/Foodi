# Foodi

Foodi is an automated pet-feeding ecosystem designed to help improve the eating habits and overall well-being of household pets. Powered by the Arduino UNO Q, Foodi combines artificial intelligence, smart hardware, and a user-friendly design to provide intelligent, personalized feeding.

Whether a pet has a gastric condition, needs help managing its weight, or simply requires scheduled meals while its owner is away, Foodi is designed to make feeding more consistent and convenient.

## How it works

Foodi consists of two main components:

- **Central Computing Module (CCM):** The central hub of the system. It contains an Arduino UNO Q, which runs an AI model that analyzes pets' eating patterns and helps determine optimized feeding schedules and portion recommendations. The CCM can also provide health-related insights and suggestions based on the collected data.
- **Feeder:** A peripheral module mounted on a wireless, movable feeder unit. This is the part of the system that pets interact with directly. It dispenses food according to the schedule determined by the CCM and includes a camera that sends a live video feed back to the CCM for monitoring and analysis.

The Feeder and CCM communicate over Bluetooth to support fast, reliable data exchange while minimizing packet loss. The CCM also uses Wi-Fi to send relevant information to a web application, allowing owners to monitor their pets and manage the system remotely.

## Example setup

The CCM is placed in a suitable location indoors and connected to a power supply. A feeder unit is positioned on the floor, connected to a wall outlet, and paired with the CCM. Once connected, the system can manage feeding schedules and collect information about the pet's eating habits.

## CCM dimensions

The CCM is designed with a sleek appearance inspired by the Mac Studio. Ventilation openings help maintain continuous airflow and support reliable operation.

- **Height:** 5.0 cm
- **Width:** 12.7 cm
- **Depth:** 12.7 cm
- **Weight:** To be determined after the first prototype is printed
