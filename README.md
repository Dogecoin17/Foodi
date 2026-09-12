# Foodi
Foodi is the solution to all of your pet feeding needs. Our aim is to make an ecosystem, powered by the Arduino UNO Q, combining powerful AI and a smart design to intelligently feed all your pets, from dogs to even parrots.

Foodi's main goal is to improve the eating habits of household pets. Be it that the animal has gastric diseases, is overweight, or it just needs meals when you're not home, Foodi aims to help the animals in the best way possible.

The system is compromised of the CCM (Central Computing Module) and slave endpoints that sit on wireless and movable feeding platforms.

The CCM contains an Arduino UNO Q, which runs an AI model that analyses the eating patterns of animals, and then calculates optimized eating habits for them. This can range from recommending certain types of foods to assigning eating times that improve the pets' health. It also contains a Wi-Fi module that connects to the owner's Wi-Fi.
The Feeder (the slave) is the module that powers the feeding platform, and is the main module the animals interact with. It contains a camera which transmits live video feed to the CCM. The feeding platform contains the food. 
The two modules communicate with each other via Bluetooth, ensuring that data exchange is fast and rid of packet loss.

The CCM transmits data to a webapp through Wi-Fi, that can be useful for the owner. Such data can be about how many times the animal  ate that day and how much food it ate. It also gives tips to the owner about how the animal should change its eating habits, which the owner can then implement. These can be about rations of food, what type of food should the animal be consuming, and how many times the feeder needs to dispense food in a day.
