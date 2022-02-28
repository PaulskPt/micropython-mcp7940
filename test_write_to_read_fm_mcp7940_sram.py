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
from machine import Pin, SoftI2C, RTC
import utime as time

my_debug = False  # global debug flag

mRTC = RTC()

i2c = SoftI2C(sda=Pin(21), scl=Pin(22)) # Correct I2C pins for TinyPICO
mcp = mcp7940.MCP7940(i2c)

start_ads = 0x20
end_ads = 0x60
EOT = 0x7F  # End-of-text marker
CMA = 0x2C  # Comma

RTC_update = False
RTC_dt = mcp.time
SYS_dt = time.localtime()

yy = 0
mo = 1
dd = 2
hh = 3
mm = 4
ss = 5
wd = 6

def set_MCP7940():
    """ called by setup(). Call only when MCP7940 datetime is not correct """
    global RTC_dt
    new_dt = (2022, 02, 28, 17, 30, 0, 0, 0)
    mcp.time = new_dt
    RTC_dt = mcp.time
    
# Convert a list to a tuple
def convert(list):
    return tuple(i for i in list)

def update_mRTC():
    if my_debug:
        print("Current microprocessor\'s RTC datetime value: ", mRTC.datetime())
    weekday = mcp.weekday()
    if my_debug:
         print("mcp.weekday() result = ", weekday)
    t_dt = (RTC_dt[yy], RTC_dt[mo], RTC_dt[dd], weekday, RTC_dt[hh], RTC_dt[mm], RTC_dt[ss], 0)
    if my_debug:
        print("Updating the microprocessor\'s RTC with: {}, type: {}".format(t_dt, type(t_dt)))
    mRTC.datetime(t_dt)  # set localtime accoring to the RTC_dt yy,mo,dd,hh,mm,ss
    if my_debug:
        print("The microprocessor\'s datetime has been updated to: \'{}\' with the datetime of the RTC".format(mRTC.datetime()))  # time.localtime()))
        print("Check: time.localtime() result: ", time.localtime())

def setup():
    global RTC_update, mRTC
    TAG = "setup(): "
    print(TAG+"MCP7940 RTC currently set to: {}, type: {}".format(RTC_dt, type(RTC_dt)))
    print(TAG+"time.localtime() result: {}, type: {}".format(SYS_dt, type(SYS_dt)))
    # Make next line active only when MCP7940 RTC is not correct
    #set_MCP7940()
    if RTC_dt[yy] < SYS_dt[yy]:
        RTC_update = True
    else:
        if RTC_dt[yy] == SYS_dt[yy]:
            if RTC_dt[mo] == SYS_dt[mo]:
                if RTC_dt[dd] == SYS_dt[dd]:
                    if RTC_dt[hh] == SYS_dt[hh]:
                        if RTC_dt[mm] == SYS_dt[mm] or RTC_dt[mm] == SYS_dt[mm]-1 or RTC_dt[mm] == SYS_dt[mm]+1: # accept upt to 1 minute mismatch
                            print(TAG+"MCP7940 RTC and SYS datetime stamps do match")
                            RTC_update = False  # We have a match of yy-mo-dd hh-mm
                        else:
                            RTC_update = True # minutes differs
                    else:
                        RTC_update = True # hours differs
                else:
                    RTC_update = True # date differs
            else:
                RTC_update = True # Month differs
        else:
            RTC_update = True # Year differs
            
    if RTC_update:
        print(TAG+"MCP7940 RTC and SYS datetime stamps do not match")

        if SYS_dt[yy] < RTC_dt[yy]:
            update_mRTC()
        else:
            print("RTC_dt has to be updated")
            if my_debug:
                print("mcp.time (2nd read) = ", mcp.time) # Read time after setting it, repeat to see time incrementing

    if not mcp.is_started():
        if my_debug:
            print("Going to start the RTC\'s MCP oscillator")
        mcp.start() # Start MCP oscillator

def main():
    TAG = "main():  "
    rtc_updated = False
    bbu_was_enabled = None  # battery backup enable flag
    
    print("MCP date time test")
    setup()
    
    while True:
        rd_sram = True
        
        print(TAG+"RTC status: is started? ", "Yes" if mcp.is_started() else "No")
        print(TAG+"Status backup battery: enabled? ", "Yes" if mcp.is_battery_backup_enabled() else "No")
        if not mcp.is_battery_backup_enabled():
            bbu_was_enabled = False
            while not mcp.is_battery_backup_enabled():
                print(TAG+"mcp.battery backup was not enabled")
                mcp.battery_backup_enable(True)
        else:
            bbu_was_enabled = True
            
        if not bbu_was_enabled:
            if mcp.is_battery_backup_enabled():
                print(TAG+"mcp.battery backup now is enabled")
                print(TAG+"Status backup battery 2nd check: enabled? ", "Yes" if mcp.is_battery_backup_enabled() else "No")
        else:
            print(TAG+"mcp.battery backup was and is enabled")
        
        if not rd_sram:
            print(TAG+"\nTo see a printout of SRAM ? Set flag \'rd_sram\' to True")
            

        curr_dt = mcp.time
        print(TAG+"Current MCP7940 RTC datetime: ", curr_dt)
        #print("Current dt-year: ", curr_dt[yy])
        if curr_dt[yy] >= 2020:
            print(TAG+"writing datetime \'{}\' to MCP7940 RTC\'s User SRAM".format(curr_dt))
            mcp.write_to_SRAM(curr_dt)# save the current dt stamp to the RTC's SRAM
            time.sleep(2)

            break
        else:
            print(TAG+"restoring saved datetime from SRAM")
            dt_tpl = convert(mcp.read_fm_SRAM())
            if not my_debug:
                print(TAG+"Datetime tuple read from RTC User SRAM: {}, type: {}".format(dt_tpl, type(dt_tpl)))
            if dt_tpl[yy] >= 2020:
                if mcp.time[yy] < dt_tpl[yy]:
                    mcp.time = dt_tpl  # update the RTC with the saved date time stamp
                    print(TAG+"MCP7940 RTC updated with new date time stamp: ", mcp.time)
                    rtc_updated = True
            else:
                print(TAG+"Year from  RTC\'s SRAM restored datetime tuple is less than 2020...awaiting adjustment to current year")
                mcp.time = time.localtime() # Set time
        
    #print("Check: reading from SRAM: ",convert( mcp.read_fm_SRAM() ))
    print("", end='\n')
                
main()