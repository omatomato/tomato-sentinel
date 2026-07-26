# Cardputer firmware target

The original M5Stack Cardputer is the primary hardware target for the Tomato
Sentinel MVP and the first device that must pass physical validation.

`board-profile:cardputer-original-v1` is therefore the default development and
test profile. Cardputer-Adv remains an explicit compatibility profile so that
its different audio, keyboard and IMU hardware cannot be mistaken for the
original board. Adv compatibility is not an MVP hardware acceptance target.

The current code is a host-side simulator. No firmware image has been compiled
or tested on physical hardware yet.
