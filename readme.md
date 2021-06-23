# Controller/BMS Dashboard

This is a simple controller and BMS dashboard for small EVs using VESC-compatible hardware.

It is based on the 
[CAN Feather](https://www.adafruit.com/product/4759)
development board and the
[3.5 inch TFT Feather Wing](https://www.adafruit.com/product/3651)
display.

When the controller and BMS are set to emit CAN status, the dashboard reads these messages, compiles them in an internal dictionary, and displays the values as text.