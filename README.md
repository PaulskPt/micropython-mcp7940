# MicroPython-MCP7940
A MicroPython driver for the Microchip MCP7940 RTC chip

This is the RTC IC used on the [TinyPICO RTC shield](https://www.tinypico.com/add-ons).

## Currently under development
Alarms have been implemented and are curretly being tested They should be available soon.

## Future development
Being able to utilise the internal memory to set and read data back

## Example usage

```python
import mcp7940
from machine import Pin, I2C
import utime as time

i2c = I2C(sda=Pin(21), scl=Pin(22)) # Correct I2C pins for TinyPICO
mcp = mcp7940.MCP7940(i2c)

mcp.time # Read time
mcp.time = time.localtime() # Set time
mcp.start() # Start MCP oscillator
mcp.time # Read time after setting it, repeat to see time incrementing
```

