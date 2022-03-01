# MicroPython datetime SRAM Save/Read test for Unexpected Maker TinyPICO RTC Shield
# containing a MCP4079 realtime clock
# See: Microchip Technology Inc MCP7940N datasheet, chapter 6.1 SRAM/RTCC Registers
# Writing and reading datetime tuple to and from User SRAM
# This script uses the mcp7940 driver file from:
# https://github.com/tinypico/micropython-mcp7940/blob/master/mcp7940.py
# Copyright (c) 2022 (for this script) Paulus Schulinck (@Paulskpt on GitHub)
# License: MIT
#
# NOTE:
# If you want to correct the datetime values of the MCP7940 RTC
# then set the values of global dt_dict and set the global flag MCP7940_RTC_update to True
# then for the next run reset the global flag MCP7940_RTC_update to False
#
from mcp7940 import MCP7940
from machine import Pin, SoftI2C, RTC
import utime as time

my_debug = True  # global debug flag

lStart = True

mRTC = RTC()

i2c = SoftI2C(sda=Pin(21), scl=Pin(22)) # Correct I2C pins for TinyPICO
mcp = MCP7940(i2c)

MCP7940_RTC_update = False  # Set to True to update the MCP7940 RTC datetime values (and set the values of dt_dict below)
mRTC_update = False
RTC_dt = mcp.time
SYS_dt = time.localtime()
SRAM_dt = None  #see setup()

yy = 0
mo = 1
dd = 2
hh = 3
mm = 4
ss = 5
wd = 6
yd = 7

# Adjust the values of the dt_dict to the actual date and time
# Don't forget to enable the MCP7940_RTC_update flag (above)
dt_dict = { yy: 2022,
            mo: 2,
            dd: 28,
            hh: 19,
            mm: 19,
            ss: 0,
            wd: 0,
            yd: 0 }

def set_MCP7940():
    """ called by setup(). Call only when MCP7940 datetime is not correct """
    mcp.time = (dt_dict[yy], dt_dict[mo], dt_dict[dd], dt_dict[hh], dt_dict[mm], dt_dict[ss], dt_dict[wd], dt_dict[yd])
    RTC_dt = mcp.time
    print("set_MCP7940(): MCP7940 RTC updated to: ", RTC_dt)
    
# Convert a list to a tuple
def convert(list):
    return tuple(i for i in list)

def update_mRTC(upd_fm_SRAM):
    global mcp, RTC_dt
    TAG = "update_mRTC(): "
    if upd_fm_SRAM:
        if my_debug:
            print(TAG+"updating MCP7940 RTC from SRAM")
        mcp.time = SRAM_dt # update MCP7940 RTC from SRAM datetime tuple
        RTC_dt = mcp.time # update 
        if my_debug:
            print(TAG+"check: MCP7940 RTC updated datetime: ", mcp.time)
    else:
        if my_debug:
            print(TAG+"updating microprocessor\'s RTC from MCP7940 RTC")
        
    if my_debug:
        print(TAG+"Current microprocessor\'s RTC datetime value: ", mRTC.datetime())
    weekday = mcp.weekday_N()
    if my_debug:
         print(TAG+"mcp.weekday_N() result = {} = {}".format(weekday, mcp.weekday_S()))
    t_dt = (RTC_dt[yy], RTC_dt[mo], RTC_dt[dd], RTC_dt[hh], RTC_dt[mm], RTC_dt[ss], weekday, 0)
    if my_debug:
        print(TAG+"Updating the microprocessor\'s RTC with: {}, type: {}".format(t_dt, type(t_dt)))
    mRTC.datetime(t_dt)  # set localtime accoring to the RTC_dt yy,mo,dd,hh,mm,ss
    if my_debug:
        print(TAG+"The microprocessor\'s datetime has been updated to: \'{}\'".format(mRTC.datetime()))  # time.localtime()))
        print(TAG+"Check: time.localtime() result: ", time.localtime())

def setup():
    global mRTC_update, mRTC, SRAM_dt
    TAG = "setup():       "
    use_SRAM_dt = False
    
    if MCP7940_RTC_update:
        set_MCP7940()
        
    print(TAG+"time.localtime() result: {}, type: {}".format(SYS_dt, type(SYS_dt)))       
    print(TAG+"MCP7940 RTC currently set to: {}, type: {}".format(RTC_dt, type(RTC_dt)))
    SRAM_dt = convert( mcp.read_fm_SRAM() )
    print(TAG+"Contents of MCP7940 RTC\'s SRAM:",SRAM_dt)
    print(TAG+"Microcontroller (time.localtime()) year  = ", SYS_dt[yy] )
    print(TAG+"MCP7940_RTC datetime year                = ", RTC_dt[yy] )
    print(TAG+"MCP7940_RTC datetime year read from SRAM = ", SRAM_dt[yy] )
    if SYS_dt[yy] == 2000:
        if RTC_dt[yy] >= 2020:
            mRTC_update = True
        elif SRAM_dt[yy] >= 2020:
            mRTC_update = True
            use_SRAM_dt = True

    if mRTC_update:
        print(TAG+"MCP7940 RTC and SYS datetime stamps do not match")
        update_mRTC(use_SRAM_dt)


    if not mcp.is_started():
        if my_debug:
            print(TAG+"Going to start the RTC\'s MCP oscillator")
        mcp.start() # Start MCP oscillator

def get_dt():
    global lStart

    if lStart:
        lStart = False
        while True:
            dt = mcp.time
            if dt[ss] == 0: # align for 0 seconds (only at startup)
                break
    else:
        dt = mcp.time
    yrday = mcp.yearday()

    return "{} {:4d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}. Day of year: {:>3d}".format(mcp.weekday_S(),dt[yy], dt[mo], dt[dd], dt[hh], dt[mm], dt[ss], yrday)

      
def main():
    TAG = "main():        "
    mRTC_updated = False
    bbu_was_enabled = None  # battery backup enable flag
    t_start = time.ticks_ms()
    
    print("MCP date time test")
    setup()
    
    while True:
        try:
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
                print(TAG+"Writing datetime \'{}\' to MCP7940 RTC\'s User SRAM".format(curr_dt))
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
                        mRTC_updated = True
                else:
                    print(TAG+"Year from  RTC\'s SRAM restored datetime tuple is less than 2020...awaiting adjustment to current year")
                    mcp.time = time.localtime() # Set time
                    
        except KeyboardInterrupt:
            print("", end='\n')
            raise SystemExit
        
    #print("Check: reading from SRAM: ",convert( mcp.read_fm_SRAM() ))
    print("", end='\n')
    while True:
        t_current = time.ticks_ms()
        t_elapsed = t_current - t_start
        if t_elapsed > 10000:
            t_start = t_current
            print("Current datetime:", get_dt())      
main()