# MicroPython-MCP7940
A MicroPython driver for the Microchip MCP7940 RTC chip

This is the RTC IC used on the [TinyPICO RTC shield](https://www.tinypico.com/add-ons).

## Currently developed
Alarms have been implemented. They have successfully been tested (see my Circuitpython example repo), however they are not used in this example: main.py-

The main.py script makes use of functions of the MCP7940 class to write and read datetime stamps to and from the MCP7940 SRAM user space

## WiFi
In file secrets.py add your ssid and password

## Example usage

```python
from mcp7940 import MCP7940
from machine import Pin, SoftI2C, RTC, unique_id 
import utime as time
 
my_sda = Pin.board.I2C_SDA  # Pin 8  I2C pins for TinyPICO
my_scl = Pin.board.I2C_SCL  # Pin 9

i2c0 = SoftI2C(sda=my_sda, scl=my_scl, freq = 400000) # Correct I2C pins for FeatherS3

mcp = MCP7940(i2c0)


# In this example we use an NTP server to set the internal RTC and the external RTC (MCP7940)

# See: https://github.com/orgs/micropython/discussions/10611
# A client MUST NOT under any conditions use a poll interval less than 15 seconds.
from my_ntptime import *

ntp = MYNTPTIME()  # create a copy of the class

if ntp.settime():   # this queries the time from an NTP server ant sets the builtin RTC 
    t = utime.time()
    print(f"time(): {t}")
    
UTC_OFFSET = 1 * 3600  # UTC OFFSET for Portugal. For NY, USA this would be: -4 * 3600

tm = utime.localtime(utime.time() + UTC_OFFSET)
print(f"setting MCP7940 timekeeping regs to: {tm}")
mcp.mcptime = tm  # Set the External RTC Shiels's clock

tm2 = mcp.mcptime # Read time after setting it, repeat to see time incrementing
print(f"check: MCP7940 set to: {tm2})

```

## Hardware used

The main.py example uses two I2C devices attached to the Unexpected maker FeatherS3 (P4):
- An Adafruit 1.12in 128x128 OLED mono display (SH1107). It uses a SH1107 driver by Peter-I5;
- an Unexpected Maker TinyPICO RTC Shield (MCP7940)

## The MCP7940 library

The in this repo used MCP7940.py library file is changed in many ways compared to the
contents of the file mcp7940.py in the ```micropython-mcp7940``` repo
by Unexpected Maker (https://github.com/tinypico/micropython-mcp7940).

## WebREPL
In the folder images you'll find an image of using WebREPL. This works OK even when the FeatherS3 and the two I2C devices are powered from a Lipo battery.
When the script has finished you can restart the script from WebREPL by issuing the command: 'main()+[Enter]'

