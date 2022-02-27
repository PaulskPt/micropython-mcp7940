# MicroPython datetime SRAM Save/Read test for Unexpected Maker TinyPICO RTC Shield
# containing a MCP4079 realtime clock
# See: Microchip Technology Inc MCP7940N datasheet, chapter 6.1 SRAM/RTCC Registers
# Writing and reading datetime tuple to and from User SRAM
# This script uses the mcp7940 driver file from:
# https://github.com/tinypico/micropython-mcp7940/blob/master/mcp7940.py
# Copyright (c) 2022 (for this script) Paulus Schulinck (@Paulskpt on GitHub)
# License: MIT
#
import mcp7940
from machine import Pin, SoftI2C
import utime as time

i2c = SoftI2C(sda=Pin(21), scl=Pin(22)) # Correct I2C pins for TinyPICO
mcp = mcp7940.MCP7940(i2c)

start_ads = 0x20
end_ads = 0x60
EOT = 0x7F  # End-of-text marker
CMA = 0x2C  # Comma

print("mcp.time = ",mcp.time) # Read time
mcp.time = time.localtime() # Set time
mcp.start() # Start MCP oscillator
print("mcp.time (2nd read) = ", mcp.time) # Read time after setting it, repeat to see time incrementing
bbu_was_enabled = None  # battery backup enable flag

# Convert a list to a tuple
def convert(list):
    return tuple(i for i in list)

def write_cma(ads):
    c = 0x2c
    for j in range(7, -1, -1):
        bit = c >> j
        bit = bit & 0x01
        mcp._set_bit(ads, j, bit)
        
def write_eot_marker(ads):
    c = EOT
    for j in range(7, -1, -1):
        bit = c >> j
        bit = bit & 0x01
        mcp._set_bit(ads, j, bit)
    
def write_dt_to_sram(dt):
    le = len(dt)
    c_addr = start_ads
    cnt = 0
    print("\nSaving current datetime tuple to user memory (SRAM)")
    for _ in range(le):
        n = dt[_]
        sn = str(n)
        le_sn = len(sn)
        print("value to save: {}, type(value): {}".format(sn, type(sn)))
        for k in range(0, le_sn):
            c = ord(sn[k])
            for j in range(7, -1, -1):
                bit = c >> j
                bit = bit & 0x01
                mcp._set_bit(c_addr, j, bit)
            cnt += 1
            print("byte nr {}, value {} saved to SRAM address: 0x{:x}".format(cnt, chr(c), c_addr))
            c_addr += 1
            if c_addr > end_ads:
                break
        if _ <= le-1:
            write_cma(c_addr)
            cnt += 1
            print("byte nr {}, value [{}] saved to SRAM address: 0x{:x}".format(cnt, ",", c_addr))
            c_addr += 1
            if c_addr > end_ads:
                break

    write_eot_marker(c_addr)
    cnt += 1
    print("byte nr {}, value {} [= EOT indicator] saved to SRAM address: 0x{:x}".format(cnt, EOT, c_addr))
    print("current datetime stamp {}, totally {} bytes, successfully saved to MCP7940 SRAM".format(dt, cnt))

def read_dt_from_sram():
    a = ''
    dt = list(a)
    tmp = list(a)
    
    print("\nReading user memory (SRAM)")
    for _ in range(start_ads, end_ads):
        val = 0
        n = 0
        print("\nSRAM address: 0x{:x}, value: 0b".format(_), end='')
        for j in range(7, -1, -1):
            bit = mcp._read_bit(_, j)
            val |= bit << j
            val << 1  # shift left 1 bit
        print("{:b}".format(val), end='')
        if val == EOT:  # Are we done? (EOT marker)
            break
        elif val == 0x2c: # (Comma - item delimiter)
            le = len(tmp)
            s = ""
            for k in range(0, le):
                s += chr(tmp[k])
                #n += (tmp[k] - 0x30) * ((le - k) ^ 10)
            dt.append(int(s))
            print("\nadded value {} to dt list {} ".format(int(s), dt))
            tmp = list(a)
            continue
        else:
            tmp.append(val)
            print("\nvalue {} added to tmp list {}".format(val, tmp))

    return convert(dt) # convert tuple to list
  
def main():
    rd_sram = True
    
    print("RTC status: is started? ", mcp.is_started())
    print("Status backup battery: enabled? ", mcp.is_battery_backup_enabled())
    if not mcp.is_battery_backup_enabled():
        bbu_was_enabled = False
        while not mcp.is_battery_backup_enabled():
            print("mcp.battery backup was not enabled")
            mcp.battery_backup_enable(True)
    else:
        bbu_was_enabled = True
        
    if not bbu_was_enabled:
        if mcp.is_battery_backup_enabled():
            print("mcp.battery backup now is enabled")
            print("Status backup battery 2nd check: enabled? ", mcp.is_battery_backup_enabled())
    else:
        print("mcp.battery backup was and is enabled")
        
    print("\nTo see a printout of SRAM ? Set flag \'rd_sram\' to True")
        
    if rd_sram:
        write_dt_to_sram(mcp.time)  # save the current dt stamp to the RTC's SRAM
        time.sleep(2)
        dt_tpl = read_dt_from_sram()
        print("\ndatetime tuple read from RTC User SRAM: {}, type: {}".format(dt_tpl, type(dt_tpl)))
    
main()
