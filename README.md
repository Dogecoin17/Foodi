# Foodi
Foodi is a comprehensive solution for automated pet feeding. Our aim is to make an ecosystem, powered by the Arduino UNO Q, combining powerful AI and a smart design to intelligently feed all your pets, from dogs to even parrots.

Foodi's main goal is to improve the eating habits of household pets. Whether your pet has gastric diseases, is overweight, or it just needs scheduled meals when you're not home, Foodi aims to help the animals in the best way possible.

The system is comprised of the CCM (Central Computing Module) and peripheral nodes that sit on wireless and movable feeder units.

The CCM contains an Arduino UNO Q, which runs an AI model that analyses the eating patterns of animals, and then calculates optimized eating habits for them. This can range from recommending certain types of foods to assigning eating times that improve the pets' health. It also contains a Wi-Fi module that connects to the owner's Wi-Fi.

The Feeder (the peripheral node) is the module that powers the feeder unit, and is the main module the animals interact with. It contains a camera which transmits live video feed to the CCM. The feeder unit's storage compartment contains the food.

The two modules communicate with each other via Bluetooth, ensuring that data exchange is fast and minimizes packet loss. The CCM uses Wi-Fi to transmit useful data to a web application for the owner. This data includes the amount of times the animal ate that day or how much food it ate, etc. It also gives tips to the owner about how the animal should change its eating habits, which the owner can then implement into the feeder's timetable through the web application. These can be about rations of food, what type of food should the animal be consuming, and how many times the feeder needs to dispense food in a day.

## Example setup

A CCM box sits somewhere in a room and is connected to a power supply. A feeder unit is placed on the ground, and plugged into a wall outlet before being paired with the CCM.
