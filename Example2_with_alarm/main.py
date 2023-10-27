# MicroPython datetime SRAM Save/Read test for Unexpected Maker TinyPICO RTC Shield
# containing a MCP4079 realtime clock
# See: Microchip Technology Inc MCP7940N datasheet, chapter 6.1 SRAM/RTCC Registers
# Writing and reading datetime tuple to and from User SRAM
# This script uses the mcp7940 driver file from:
# my forked version on: https://github.com/PaulskPt/micropython-mcp7940/blob/master/mcp7940.py
# which is a forked version of: https://github.com/tinypico/micropython-mcp7940/blob/master/mcp7940.py
# which is a forked version of: https://github.com/mattytrentini/micropython-mcp7940/blob/master/mcp7940.py
#
# Copyright (c) 2023 (for this script and my_ntptime.py) Paulus Schulinck (@Paulskpt on GitHub)
# License: MIT
#
# e) now you can again run this script permanently.
# Update 2023-09-30:
# When I had oscilloscope probes connected to the SCL and SDA pins of the 7940 RTC,
# while the oscilloscope was switched off,
# the script crashed with an OSError ENODEV.
# When I removed the connections with the probes, the script ran OK.
# Update 2023-10-12:
# The script now synchronizes both the internal RTC as the external MCP7940 RTC shield clock from an exterenal NTP server.
# Added the file my_ntptime which contains the MYNTPTIME class.
# It is a modified version of the micropython ntptime module
# The micropython ntptime module does not contain a class but a few functions.
# I added functions to be able to change the host, read the current host set.
# In the script below I also added the function 'can_update_fm_NTP()'. 
# This function prevents more than one request to the NTP server in 15 seconds,
# to not cause error replies from the NTP server.
#
from mcp7940 import MCP7940
from machine import Pin, SoftI2C, RTC, unique_id, idle   # Note I2C is deprecated!
import utime
import network
import socket
#import time
import struct
import sys, gc
from secrets import secrets
import ubinascii
import json
import feathers3
import neopixel
import micropython

# See: https://docs.micropython.org/en/latest/reference/isr_rules.html
micropython.alloc_emergency_exception_buf(100)

# See: https://github.com/orgs/micropython/discussions/10611
# A client MUST NOT under any conditions use a poll interval less than 15 seconds.
from my_ntptime import *

my_debug = False  # global debug flag

# Turn on the power to the NeoPixel
feathers3.set_ldo2_power(True)

ntp = MYNTPTIME()  # create a copy of the class

def save_config():
    """function to save the config dict to the JSON file"""
    with open("config.json", "w") as f:
        json.dump(config, f)

config = None

# load the config file from flash
with open("config.json") as f:
    config = json.load(f)
if my_debug:
    print(f"global(): config: {config}")

# --- DISPLAY DRTIVER selection flag ----+
use_sh1107 = True  #                     |
# ---------------------------------------+
MCP7940_RTC_update = True  # Set to True to update the MCP7940 RTC datetime values (in function set_time())
use_TAG = True

led = Pin("LED_BLUE", Pin.OUT)

# Create a NeoPixel instance
# Brightness of 0.3 is ample for the 1515 sized LED
pixels = neopixel.NeoPixel(Pin(feathers3.RGB_DATA), 1)

mRTC = RTC()
if mRTC and my_debug:
    # note the last value in the tuple returned by mRTC.datetime() is 'subsecond'
    # example: (2023, 10, 16, 0, 10, 14, 31, 617335)
    print(f"global: mRTC object created. mRTC.datetime(): {mRTC.datetime()}")

my_sda = Pin.board.I2C_SDA  # Pin 8
my_scl = Pin.board.I2C_SCL  # Pin 9

i2c0 = SoftI2C(sda=my_sda, scl=my_scl, freq = 400000) # Correct I2C pins for FeatherS3
#i2c1 = SoftI2C(sda=my_sda, scl=my_scl, freq = 400000)


#print(f"i2c0 is i2c1: {i2c0 is i2c1}")  # revealed False
cnt = 0
mcp = None

while True:
    try:
        mcp = MCP7940(i2c0, battery_enabled=True)
        print(f"create mcp object try nr: {cnt+1}")
        cnt += 1
        if mcp is not None:
            print("mcp object created")
            break
    except OSError as e:
        print(f"Error {e}")
        if cnt >= 9:
            raise

if use_sh1107:
    import sh1107  # driver from peter-I5
    # Width, height and rotation for Monochrome 1.12" 128x128 OLED
    WIDTH = 128
    HEIGHT = 128
    ROTATION = 180 # Was: 90
    display = sh1107.SH1107_I2C(WIDTH, HEIGHT, i2c0, address=0x3d, rotate=ROTATION)
    #display = sh1107.SH1107_I2C(WIDTH, HEIGHT, i2c0)
    # Border width
    BORDER = 2

    # Cleanup
    WIDTH = None
    HEIGHT = None
    ROTATION = None
    BORDER = None
    intro = ["Micropython", "FeatherS3", "MCP7940", "RTC shield", "OLED display"]
    display.sleep(False)
    display.fill(0)
    row = 0
    for _ in range(len(intro)):
        display.text(intro[_], 0, row, 1)
        row += 20
    display.show()
    utime.sleep(3)
    #display.sleep(True)


dev_dict = {0x3d: "OLED display (SH1107)",
            0x6f: "RTC shield (MCP7940)"}

e = None
cnt = None
devices = []
devices = i2c0.scan()
if len(devices) > 0:
    print(f"i2c devices present:")
    for _ in range(len(devices)):
        print("device nr {:d}, addres dec: {:3d}, addres hex: 0x{:02x}, {:s}".format(_+1, devices[_], devices[_], dev_dict[devices[_]]))
    print()

# See: https://www.epochconverter.com/
# Values are for timezone Europe/Portugal
dst = {
        2022:(1648342800, 1667095200),  # 2022-03-29 01:00:00 / 2022-10-30 02:00:00
        2023:(1679792400, 1698544800),  # 2023-03-26 01:00:00 / 2023-10-29 02:00:00
        2024:(1711846800, 1729994400),  # 2024-03-31 01:00:00 / 2024-10-27 02:00:00
        2025:(1743296400, 1761444000),  # 2025 03-30 01:00:00 / 2025-10-28 02:00:00
        2026:(1774746000, 1792893600),  # 2026-03-29 01:00:00 / 2026-10-25 02:00:00
        2027:(1806195600, 1824948000),  # 2027-03-28 01:00:00 / 2027-10-31 02:00:00
        2028:(1837645200, 1856397600),  # 2028-03-26 01:00:00 / 2028-10-29 02:00:00
        2029:(1869094800, 1887847200),  # 2029-03-25 01:00:00 / 2029-10-28 02:00:00
        2030:(1901149200, 1919296800),  # 2030-03-31 01:00:00 / 2030-10-27 02:00:00
        2031:(1932598800, 1950746400),  # 2031-03-30 01:00:00 / 2031-10-26 02:00:00
}

state = None

class State:
    def __init__(self, saved_state_json=None):
        self.board_id = None
        self.wlan = None
        self.lStart = True
        self.loop_nr = -1
        self.max_loop_nr = 30
        self.tag_le_max = 26  # see tag_adj()
        self.use_clr_SRAM = True
        self.set_SYS_RTC = True
        self.NTP_dt_is_set = False
        self.SYS_RTC_is_set = False
        self.set_EXT_RTC = True # Set to True to update the MCP7940 RTC datetime values (and set the values of dt_dict below)
        self.EXT_RTC_is_set = False
        self.save_dt_fm_int_rtc = False  # when save_to_SRAM, save datetime from INTernal RTC (True) or EXTernal RTC (False)
        self.ntp_last_sync_dt = 0
        self.dt_str_usa = True
        self.MCP_dt = None
        self.ntp_server_idx = 0 # see ntp_servers_dict
        self.NTP_dt = None
        self.SYS_dt = None # time.localtime()
        self.SRAM_dt = None  #see setup()
        self.ip = None
        self.s__ip = None
        self.mac = None
        self.use_neopixel = True
        self.neopixel_brightness = None
        self.neopixel_dict = {
            "BLK": (0, 0, 0),
            "RED": (200, 0, 0),
            "GRN": (0, 200, 0),
            "BLU": (0, 0, 200)}
        self.neopixel_rev_dict = {
            (0, 0, 0)   : "BLK",
            (200, 0, 0) : "RED",
            (0, 200, 0) : "GRN",
            (0, 0, 200) : "BLU"}
        self.curr_color_set = None
        # See: https://docs.python.org/3/library/time.html#time.struct_time
        self.tm_year = 0
        self.tm_mon = 1 # range [1, 12]
        self.tm_mday = 2 # range [1, 31]
        self.tm_hour = 3 # range [0, 23]
        self.tm_min = 4 # range [0, 59]
        self.tm_sec = 5 # range [0, 61] in strftime() description
        self.tm_wday = 6 # range 8[0, 6] Monday = 0
        self.tm_yday = 7 # range [0, 366]
        self.tm_isdst = 8 # 0, 1 or -1
        self.COUNTRY = None
        self.STATE = None
        self.tm_tmzone = None # was: 'Europe/Lisbon' # abbreviation of timezone name
        #tm_tmzone_dst = "WET0WEST,M3.5.0/1,M10.5.0"
        self.UTC_OFFSET = None
        self.alarm1 = ()
        self.alarm2 = ()
        self.alarm1_int = False
        self.alarm2_int = False
        self.alarm1_set = False
        self.alarm2_set = False
        self.mfp = False
        self.POL = 0
        self.IF = 1
        self.MSK = 2
        self._match_lst_long = ["second", "minute", "hour", "weekday", "date", "reserved", "reserved", "all"]
        self.mRTC_DOW = DOW =  \
        {
            0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday"
        }
        self.month_dict = {
            1: "Jan",
            2: "Feb",
            3: "Mar",
            4: "Apr",
            5: "May",
            6: "Jun",
            7: "Jul",
            8: "Aug",
            9: "Sep",
            10: "Oct",
            11: "Nov",
            12: "Dec"
        }


# Set the interrupt line coming from the UM RTC Shield, pin 4 (MFP)
# According to the RTC Shield schematic the MFP pin is pulled up
# through a 10kOhm resistor, connected to VCC (3.3V).
rtc_mfp_int = Pin(33, mode=Pin.IN, pull=Pin.PULL_DOWN)

def interrupt_handler(state):  # (pin):
    TAG = tag_adj(state, "interrupt_handler(): ")
    if state.mfp:  # We have an interrupt!
        print(TAG+"RING RING RING we have an interrupt from the RTC shield!")
        alarm_blink(state)
        clr_alarm(state, 1)
        mcp._clr_ALMxIF_bit(1) # Clear the interrupt
        state.mfp = False
        raise KeyboardInterrupt

# rtc_mfp_int.irq(handler=interrupt_handler, trigger=Pin.IRQ_RISING)


def read_fm_config(state):
    TAG = tag_adj(state, "read_fm_config(): ")
    key_lst = list(config.keys())
    if my_debug:
        print(TAG+f"global, key_lst: {key_lst}")
        print(TAG+"setting state class variables:")
    for k,v in config.items():
        if isinstance(v, int):
            s_v = str(v)
        elif isinstance(v, str):
            s_v = v
        elif isinstance(v, bool):
            if v:
                s_v = "True"
            else:
                s_v = "False"
        if my_debug:
            print("\tk: \'{:10s}\', v: \'{:s}\'".format(k, s_v))
        if k in key_lst:
            if k == "COUNTRY":
                if v == "PRT":
                    config["STATE"] == ""
                    config["UTC_OFFSET"] == 1
                elif v == "USA":
                    config["STATE"] = "NY"
                    config["UTC_OFFSET"] = -4
                state.COUNTRY = v
                state.STATE = config["STATE"]
            if k == "dt_str_usa":
                state.dt_str_usa = v
            if k == "is_12hr":
                state.is_12hr = v
            if k == "UTC_OFFSET":
                state.UTC_OFFSET = v * 3600
            if k == "tmzone":
                state.tm_tmzone = v
    if my_debug:
        print(TAG+f"for check:\n\tstate.COUNTRY: \'{state.COUNTRY}\', state.STATE: \'{state.STATE}\', state.UTC_OFFSET: {state.UTC_OFFSET}, state.tm_tmzone: \'{state.tm_tmzone}\'")

save_config()

def is_dst():
    t = utime.time()
    yr = utime.localtime(t)[0]

    if yr in dst.keys():
        start, end = dst[yr]
        return False if t < start or t > end else True
    else:
        print("year: {} not in dst dictionary ({}).\nUpdate the dictionary! Exiting...".format(yr, dst.keys()))
        raise SystemExit
    
def can_update_fm_NTP(state):
    TAG = tag_adj(state, "can_update_fm_NTP(): ")
    ret = False
    if my_debug:
        print(TAG+f"last NTP sync: {state.ntp_last_sync_dt}")
    if state.ntp_last_sync_dt == 0:  # we did not NTP sync yet
        return True   # yes go to do NTP sync
    else:
        t1 = state.ntp_last_sync_dt
        while True:
            t2 = utime.time() - state.UTC_OFFSET
            if t2 >= t1:
                t_diff = t2 - t1
                if not my_debug:
                    print(TAG+f"last time of sync: {t1}, current time {t1}, difference in seconds: {t_diff}")
                if t_diff >= 15:
                    ret = True
                    break
            utime.sleep(2)  # we have to wait 15 seconds
    return ret
         

def set_time(state):
    global config
    TAG = tag_adj(state, "set_time(): ")
    try_cnt = 0
    good_NTP = False
    tm = None
    if can_update_fm_NTP(state):
        tm_mcp = mcp.mcptime
        mcp_dt = list(tm_mcp)  # create a list (which is mutable)
        mcp_dt_hh = mcp_dt[state.tm_hour]
        lcl_dt = utime.localtime(utime.time() + state.UTC_OFFSET)
        lcl_dt_hh = lcl_dt[state.tm_hour]
        # During a long sleep time it happened that the MCP7940 clock was not updated(updating)
        # In that case the MCP7940 timekeeping registers have to be updated
        # So, if the flag state.NTP_dt_is_set already had been set, it has to be reset.
        if lcl_dt_hh != mcp_dt_hh:
            state.NTP_dt_is_ist = False
        if my_debug:
            print(TAG+"synchronizing builtin RTC from NTP server, waiting...")
        try_cnt = 0
        while True:
            try:
                if not state.NTP_dt_is_set:
                    if ntp.settime():   # this queries the time from an NTP server ant sets the builtin RTC 
                        t = utime.time()
                        if my_debug:
                            print(TAG+f"time(): {t}")
                        if t >= 0:
                            good_NTP = True
                            break
                    print(TAG+"trying again. Wait...")
                    utime.sleep(2)
                    try_cnt += 1
                    if try_cnt >= 3:
                        break
            except OSError as e:
                print(TAG+f"Error: {e}")
                try_cnt += 1
                if try_cnt >= 5:
                    raise
        if good_NTP:
            state.NTP_dt_is_set = True
            print(TAG+"Succeeded to update the builtin RTC from an NTP server")
            state.ntp_last_sync_dt = utime.time() # get the time serial
            if not my_debug:
                print(TAG+f"Updating ntp_last_sync_dt to: {state.ntp_last_sync_dt}")
            tm = utime.localtime(utime.time() + state.UTC_OFFSET)    
            ths = mcp.time_has_set()
            print(TAG+f"mcp.time_has_set(): {ths}")
            if not ths:
                print(TAG+f"setting MCP7940 timekeeping regs to: {tm}")
                #if MCP7940_RTC_update:
                #-----------------------------------------------------------
                # Set MCP7940 RTC shield timekeeping registers
                #-----------------------------------------------------------
                mcp.mcptime = tm  # Set the External RTC Shiels's clock
                state.MCP_dt = tm
                #-----------------------------------------------------------
                # The following 2 lines added because I saw that calls to 
                # mcp.mcpget_time() always returns the same datetime stamp
                if not mcp._is_started():
                    print(TAG+"mcp was not started. Starting now")
                    mcp.start()
                    if mcp._is_started():
                        print(TAG+"mcp now is running")
                else:
                    print(TAG+"mcp is running")
            if not tm[state.tm_year] in dst.keys():
                print("year: {} not in dst dictionary ({}).\nUpdate the dictionary! Exiting...".format(tm[state.tm_year], dst.keys()))
                raise SystemExit
            if state.set_SYS_RTC:
                if not state.SYS_RTC_is_set:
                    tm2 = (tm[state.tm_year], tm[state.tm_mon], tm[state.tm_mday], tm[state.tm_wday] + 1,
                        tm[state.tm_hour], tm[state.tm_min], tm[state.tm_sec], 0)
                    mRTC.datetime(tm2)  # was: mRTC().datetime(tm2)
                    state.SYS_dt = tm2
                    state.SYS_RTC_is_set = True
                    if not my_debug:
                        print(TAG+f"builtin RTC set to: {state.SYS_dt}")
            if my_debug and tm is not None:
                print(TAG+"date/time updated from: \"{}\"".format(ntp.get_host()))
        else:
            print(TAG+"failed to update builtin RTC from an NTP server")
    else:
        if my_debug:
            print(TAG+"not updating builtin RTC from NTP in this moment")

def neopixel_color(state, color):
    global pixels
    if color is None:
        color = state.curr_color_set
    elif not isinstance(color, str):
        color = state.curr_color_set
    
    if color in state.neopixel_dict:
        if neopixel  and not state.curr_color_set == color:
            state.curr_color_set = color
            r,g,b = state.neopixel_dict[color]  # feathers3.rgb_color_wheel( clr )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            
def neopixel_blink(state, color):
    TAG = tag_adj(state, "neopixel_blink(): ")
    global pixels
    if color is None:
        color = state.curr_color_set
    elif not isinstance(color, str):
        color = state.curr_color_set
    else:
        state.curr_color_set = color
        
    if color in state.neopixel_dict:
        if neopixel:
            if not my_debug:
                print(TAG+f"going to blink color: \'{color}\'")
            for _ in range(6):
                if _ % 2 == 0:
                    r, g, b = state.neopixel_dict[color]
                else:
                    r, g, b = state.neopixel_dict["BLK"]
                pixels[0] = ( r, g, b, state.neopixel_brightness)
                pixels.write()
                utime.sleep(0.5)
            # reset to color at start of this function
            r, g, b = state.neopixel_dict["BLK"]  # was: [state.curr_color_set]
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()

def alarm_blink(state):
    #if state.loop_nr < 3:
    #    return
    TAG = tag_adj(state, "alarm_blink(): ")
    my_RED = (200,   0,   0)
    my_GRN = (0,   200,   0)
    my_BLU = (0,     0, 200)
    my_BLK = (0,     0,   0)

    current_color = state.curr_color_set
    if state.use_neopixel:
        for _ in range(5):
            if not my_debug:
                print(TAG+f"blinking: RED")
            r,g,b = state.neopixel_dict["RED"] # feathers3.rgb_color_wheel( state.RED )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            utime.sleep(1)
            if not my_debug:
                print(TAG+f"blinking: BLUE")
            r,g,b = state.neopixel_dict["BLU"] #feathers3.rgb_color_wheel( state.BLK )
            pixels[0] = ( r, g, b, state.neopixel_brightness)
            pixels.write()
            utime.sleep(1)
        # restore last color:
        if my_debug:
            print(TAG+f"resetting color to: {current_color}")
        # r,g,b = feathers3.rgb_color_wheel( current_color )
        r,g,b = state.neopixel_dict["BLK"]
        pixels[0] = ( r, g, b, state.neopixel_brightness)
        pixels.write()

def do_connect(state):
    TAG = tag_adj(state, "do_connect(): ")
    #print(TAG+f"dir(wlan): {dir(wlan)}")
    
    wlan = state.wlan # was: wlan = network.WLAN(network.STA_IF)
    # Load login data from different file for safety reasons
    ssid = secrets['ssid']
    pw = secrets['pw']
    s_ip = ""
    wlan.active(True)
    wlist = wlan.scan()

    if my_debug:
        print(TAG+f"type(wlist): {type(wlist)}, wlist: {wlist}")
    if isinstance(wlist, list):
        le = len(wlist)
        if le == 0:
            print(TAG+f"wifi scan resolved no list of access points")
        else:
            vf = wlist[0]
            if my_debug:
                print(f"WiFi access point details:\n{vf}")
                print(f"Data access point \'{ssid}\'")
                ap_detail_lst = ['ssid', 'bssid', 'channel', 'RSSI', 'security', 'hidden']
                ap_security_lst = ['open', 'WEP', 'WPA-PSK', 'WPA2-PSK', 'WPA/WPA2-PSK']
                for _ in range(len(vf)):
                    itm = vf[_]
                    if isinstance(vf[_], bytes):
                        try:
                            itm2 = ''
                            if ap_detail_lst[_] == 'bssid':
                                n_lst = list(itm)
                                #print(TAG+f"n_lst: {n_lst}")
                                le = len(n_lst)
                                for n in range(le):
                                    if n < le-1:
                                        itm2 += "{:02x}:".format(n_lst[n])
                                    else:
                                        itm2 += "{:02x}".format(n_lst[n])
                                #print(f"item: {_} = {itm2} = {ap_detail_lst[_]}")
                            else:
                                itm2 =itm.decode('utf-8')
                            print(f"item: {_} = {itm2} = {ap_detail_lst[_]}")
                        except UnicodeError:
                            #itm2 = ubinascii.unhexlify(str(itm))
                            itm2 = str(itm)
                            print(f"item: {_} = {itm2}, = {ap_detail_lst[_]}")
                    else:
                        itm2 = vf[_]
                        print(f"item: {_} = {itm2} = {ap_detail_lst[_]}")
                        if _ == 4:
                            print(f"Note: security type is: {ap_security_lst[itm2]}")
                print()
    #print(TAG+f"list of ap\'s: {wlist[0][1]}")
    #wlan.AUTH_WPA2_PSK

    if not wlan.isconnected():
        print(TAG+'connecting to WiFi network...')
        wlan.connect(ssid, pw)
        while not wlan.isconnected():
            idle()  # save power while waiting
    else:
        print(TAG+f"WiFi already connected")
    if wlan.isconnected():
        # print(TAG+f"WiFi connected to \'{ssid}\'")

        status = wlan.ifconfig()
        if len(status) > 0:  # was: if len(conn_lst) > 0:
            s_ip = status[0]
            print(TAG+f"ip: {s_ip}")
            state.s__ip = s_ip
        msg = ["WiFi","", "connected to", "", ssid, "", "ip:", state.s__ip]
        pr_msg(state, msg)
        neopixel_blink(state, "GRN")
    else:
        print(TAG+f"WiFi failed to connect to \'{ssid}\'")
        neopixel_blink(state, "RED")
    
    # See: https://stackoverflow.com/questions/75972383/while-running-wlan-status-command-on-esp32-it-is-giving-value-of-1010-instead
    """
    STAT_CONNECTING = 1010
    max_wait = 10
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print(TAG+'waiting for connection...')
        utime.sleep(1)
    if my_debug:
        print(TAG+f"wlan.status() = {wlan.status()}")
    wstat = wlan.status()
    if wstat != 1010:
        #neopixel_color(state, state.neopixel_dict["RED"])
        neopixel_blink(state, "RED")
        print(TAG+f"Error: {wstat}")
        #raise RuntimeError('network connection failed')
    elif wstat == 1001:
        #neopixel_color(state, state.neopixel_dict["RED"])
        neopixel_blink(state, "RED")
        print(TAG+f"Error: {wstat}")
    else:
        if my_debug:
            print(TAG+f"wifi.status(): {wstat}")
            print(TAG+'connected')
        status = wlan.ifconfig()
        # print(TAG+f"wlan.STAT_CONNECTING: {wlan.STAT_CONNECTING}")
        print(TAG+f"WiFi connected to \'{ssid}\'")
        
        #neopixel_color(state, state.neopixel_dict["GRN"])
        neopixel_blink(state, "GRN")
        if len(conn_lst) > 0:
            s_ip = status[0]
            print(f"ip: {s_ip}")
            print()
    """

# When a call to mcp._is_12hr is positive,
# the hours will be changed from 24 to 12 hour fomat:
# AM/PM will be added to the datetime stamp
def add_12hr(t):
    TAG = tag_adj(state, "add_12hr()): ")
    if not isinstance(t, tuple):
        return (0,)
    le = len(t)
    if le < 6:
        if my_debug:
            print(TAG+f"length param t insufficient {le}")
        return (0,)
    num_registers = len(t)
    if my_debug:
        print(TAG+f"num_registers: {num_registers}")
    if num_registers == 6: 
        year, month, date, hours, minutes, seconds = t
    elif num_registers == 7:
        year, month, date, hours, minutes, seconds, weekday = t
    #num_registers = 7 if start_reg == 0x00 else 6
    
    is_12hr = mcp._is_12hr
    is_PM = mcp._is_PM(hours) # don't use get_ampm because that returns a string type
   
    if my_debug:
        print(TAG+f"param t: {t}")
        print(TAG+f"is_12hr: {is_12hr}, is_PM: {is_PM}")

    t2 = (month, date, hours, minutes, seconds,  weekday)
    t3 = (year,) + t2 if num_registers == 7 else t2

    if my_debug:
        print(TAG+f"t2: {t2}")

    t3 += (is_12hr, is_PM)  # add yearday and isdst to datetime stamp
    
    if my_debug:
        print(TAG+f"return value: {t3}")

    return t3
            
def get_hours12(hh):
    ret = hh
    if hh >= 12:
        ret = hh - 12
    return ret
         
def upd_SRAM(state):
    TAG = tag_adj(state, "upd_SRAM(): ")
    num_registers = 0
    res = None
    tm = None
    tm2 = None
    tm3 = None
    s_tm = ""
    s_tm2 = ""
    dt1 = ""
    dt2 = ""
    dt3 = ""
    dt6 = ""
    dt7 = ""
    
    if state.use_clr_SRAM:
        if my_debug:
            print(TAG+"First we go to clear the SRAM data space")
        mcp.clr_SRAM()
    else:
        if my_debug:
            print(TAG+"We\'re not going to clear SRAM. See global var \'state.use_clr_SRAM\'")
    
    # Decide which datetime stamp to save: from INTernal RTC or from EXTernal RTC. Default: from EXTernal RTC
    if state.save_dt_fm_int_rtc:
        tm = utime.localtime() # Using INTernal RTC
        s_tm = "utime.localtime()"
        s_tm2 = "INT"
    else:
        if my_debug:
            if use_sh1107 and display.is_awake:
                print(TAG+"the display is awake. We put it to sleep")
                display.sleep(True)
            else:
                print(TAG+"the display is asleep")
        tm = mcp.mcptime  # Using EXTernal RTC
        if my_debug:
            print(TAG+f"tm (= mcp.mcptime): {tm}")
        s_tm = "mcp.mcptime"
        s_tm2 = "EXT"
    if my_debug:
        print(TAG+f"tm: {tm}")
        
    tm2 = add_12hr(tm)  # Add is_12hr, is_PM and adjust hours for 12 hour time format
    le = len(tm2)
    if le < 2:
        if my_debug:
            print(TAG+f"tm2 length {le} insufficient")
        return -1
    
    if my_debug:
        print(TAG+f"tm2: {tm2}")
    is_12hr = 0
    is_PM = 0
    hours12 = 0
    
    if le == 7:
        year, month, date, hours, minutes, seconds, weekday = tm2
        tm3 = (year-2000, month, date, hours, minutes, seconds, weekday)
    elif le == 9:
        year, month, date, hours, minutes, seconds, weekday, is_12hr, is_PM = tm2
        if is_12hr:
            hours12 = get_hours12(hours)
        else:
            hours12 = hours
        tm3 = (year-2000, month, date, hours12, minutes, seconds, weekday, is_12hr, is_PM)
    
    # print(TAG+f"month: {month}")
    if month >= 1 and month <= 12:  # prevent key error
        dt1 = "{:s} {:02d} {:d}".format(
            state.month_dict[month],
            date,
            year)
    else:
        dt1 = ""
    
    #dt1 = "{}/{:02d}/{:02d}".format(
    #        year,
    #        month,
    #        date)

    if state.dt_str_usa:
        if is_12hr:
            hours12 = get_hours12(hours)
            
            if my_debug:
                print(TAG+f"hours: {hours}, minutes: {minutes}, seconds: {seconds}, is_12hr: {is_12hr}")
            if hours >= 0 and hours < 24 and minutes >= 1 and minutes < 60 and seconds >= 1 and seconds < 60:
                ampm = get_ampm(hours)
                dt2 = "{:d}:{:02d}:{:02d} {}".format(
                hours12,
                minutes,
                seconds, 
                ampm)
            else:
                dt2 = "?:??:?? ?"
        else:
            if my_debug:
                print(TAG+f"hours: {hours}, minutes: {minutes}, seconds: {seconds}, is_12hr: {is_12hr}")
            if hours >= 0 and hours < 13 and minutes >= 1 and minutes < 60 and seconds >= 1 and seconds < 60:
                dt2 = "{:02d}:{:02d}:{:02d}".format(
                hours,
                minutes,
                seconds)
            else:
                dt2 = "??:??.??"
    
    if weekday >= 0 and weekday <= 6:
        wd = mcp.DOW[weekday]
    else:
        wd = "?"
    # print(TAG+f"weekday: {weekday}, mcp.DOW[weekday]: {wd}")

    dt3 = "wkday: {}".format(wd)
    
    dt6 = "is_12hr: {}".format(is_12hr)
    
    if is_PM:
        dt7 = "is_PM: {}".format(is_PM)
    else:
        dt7 = "is_PM: {}".format(ampm)


    msg = ["Write to SRAM:", dt1, dt2, dt3, dt6, dt7]
    pr_msg(state, msg)

    mcp.clr_SRAM()  # Empty the total SRAM
    
    if my_debug:
        mcp.show_SRAM() # Show the values in the cleared SRAM space
    
    if my_debug:
        print(TAG+f"type({s_tm}): {type(tm)},")
        print(TAG+f"{s_tm2}ernal_dt: {tm}")
    if isinstance(tm, tuple):
        if my_debug:
            print(TAG+f"we\'re going to write {s_tm} to the RTC shield\'s SRAM")
        # -----------------------------------------------------
        # WRITE TO SRAM
        # -----------------------------------------------------
        mcp.write_to_SRAM(tm3)
    if my_debug:
        print(TAG+"Check: result reading from SRAM:")
    # ----------------------------------------------------------
    # READ FROM SRAM
    # ----------------------------------------------------------
    res = mcp.read_fm_SRAM() # read the datetime saved in SRAM
    if res is None:
        res = ()
    
    le = len(res)
    if le < 2:
        if my_debug:
            print(TAG+f"res length {le} insufficient")
        return -1
    
    if len(res) > 0:
        num_registers = res[0]
        if num_registers == 0:
            print(TAG+f"no datetime stamp data received")
            return -1
        
        rdl = "received datetime stamp length: {:d}".format(num_registers-1)
        yearday = mcp.yearday(res[1:])  # slice off byte 0 (= num_registers)
        isdst = -1
        
        if my_debug:
            print(TAG+f"{rdl}")
            print(TAG+f"received from SRAM: {res[1:]}")
            print(TAG+f"yearday {yearday}, isdst: {isdst} ")
        
        if num_registers == 8:
            _, year, month, date, weekday, hours, minutes, seconds  = res  # don't use nr_bytes again
        elif num_registers == 10:
            _, year, month, date, weekday, hours, minutes, seconds, is_12hr, is_PM = res # don't use nr_bytes again

        year += 2000

        # weekday += 1  # Correct for mcp weekday is 1 less than NTP or utime.localtime weekday
        if month >= 1 and month <= 12:  # prevent key error
            mon_s = state.month_dict[month]
        else:
            mon_s = " ? "
            
        if state.dt_str_usa:
            dt1 = "{:s} {:02d} {:d}".format(    
                mon_s,
                date,
                year)
        else:
            dt2 = "{:d}{:02d}/{:02d}".format(
                date,
                month,
                year)

        if is_12hr:
            ampm = get_ampm(hours+12)
            
            if hours >= 0 and hours < 24 and minutes >= 1 and minutes < 60 and seconds >= 1 and seconds < 60:
                dt2 = "{:d}:{:02d}:{:02d} {}".format(
                hours,
                minutes,
                seconds,
                ampm)
            else:
                dt2="?:??:???? ?"
        else:
            if hours >= 0 and hours < 24 and minutes >= 1 and minutes < 60 and seconds >= 1 and seconds < 60:
                dt2 = "{:02d}:{:02d}:{:02d}".format(  
                hours,
                minutes,
                seconds)
            else:
                dt2="??:??:??"
        
        if weekday >= 0 and weekday <= 6:
            wd = mcp.DOW[weekday]
        else:
            wd = "?"
        # print(TAG+f"weekday: {weekday}, mcp.DOW[weekday]: {wd}")

        dt3 = "wkday: {}".format(wd)

        dt4 = "yrday: {}".format(yearday)

        dt5 = "dst: {}".format(isdst)
        
        dt6 = "is_12hr: {}".format(is_12hr)
    
        if is_PM:
            dt7 = "is_PM: {}".format(is_PM)
        else:
            dt7 = "is_PM: {}".format(ampm)

        msg = ["Read from SRAM:", dt1, dt2, dt3, dt6, dt7, "Added: ", dt4, dt5]
        
        pr_msg(state, msg)
        
        state.SRAM_dt = (year, month, date, weekday, hours, minutes, seconds, is_12hr, is_PM) # skip byte 0 = num_regs
        
        if my_debug:
            sdt = state.SRAM_dt
            sdt_s = "state.SRAM_dt"
            print(TAG+f"{sdt_s}: {sdt}. type({sdt_s}): {type(sdt)}. len({sdt_s}): {len(sdt)}")
    return 1  # indicate success
    
# Convert a list to a tuple
def convert_to_tpl(dt):
    if isinstance(dt, tuple): # it is already a tuple. No need to convert
        return dt
    if isinstance(dt, list):  # convert the list to tuple
        return tuple(i for i in dt)

# Make preparations to enable alarm interrups from RTC shield
# through the MFP (IO4) of the RTC shield.
def prepare_alm_int(state):

    # See the MCP7940N datasheet, paragraph 5.5, DS20005010H-page 25
    # See the Dual Alarm Output Truth Table (Table 5-10) on page 27
    mcp._clr_SQWEN_bit()  # Clear the Square Wave Enable bit
    for _ in range(2):
        if not mcp.alarm_is_enabled(_+1):
            res = mcp.alarm_enable(_+1, True)  # Enable the alarm (1 or 2)


def set_alarm(state, alarm_nr = 1, mins_fm_now=10):
    TAG = tag_adj(state, "set_alarm(): ")

    if not alarm_nr in [1, 2]:
        return

    if mins_fm_now > 60:  # not more dan 60 minutes from now
        mins_fm_now = 10

    alarm1en = mcp.alarm_is_enabled(1)
    alarm2en = mcp.alarm_is_enabled(2)

    t1 = utime.time()  # get seconds since epoch
    dt = utime.localtime(t1+(mins_fm_now*60)) # convert mins_fm_now to seconds

    month   = dt[state.tm_mon]
    date    = dt[state.tm_mday]
    hours   = dt[state.tm_hour]
    minutes = dt[state.tm_min]
    seconds = dt[state.tm_sec]
    weekday = dt[state.tm_wday]-1 # +1
    dow = mcp.DOW[weekday]  # was: mcp.DOW[weekday]
    # print(TAG+f"weekday: {weekday}")

    t = month, date, hours, minutes, seconds, weekday

    if alarm1en and alarm_nr == 1:
        if my_debug:
            print(TAG+f"setting alarm1 for: {t[:5]}, {dow}")
        # ---------------------------------------------------------------
        # SET ALARM1
        # ---------------------------------------------------------------
        mcp.alarm1 = t  # Set alarm1
        # ---------------------------------------------------------------
        t_ck = mcp.alarm1[:6]  # check result
        if my_debug:
            print(TAG+f"check: alarm{alarm_nr} is set for: {t_ck}")
        state.alarm1 = t_ck
        state.alarm1_set = True
        mcp._clr_ALMxIF_bit(alarm_nr)     # Clear the interrupt of alarm1
        mcp._set_ALMxMSK_bits(alarm_nr,1) # Set the alarm1 mask bits for a minutes match
        # IMPORTANT NOTE:
        # ===============
        # I experienced that if mcp.alarm1 (or mcp.alarm2) is called earlier, the setting of the ALMPOL bit is reset,
        # that is why we set the ALMPOL bit again (below)
        # YES: and the setting of the ALMPOL_bit has to done as last of these commands here!!!
        # ===============
        if not mcp._read_ALM_POL_IF_MSK_bits(1, state.POL):
            mcp._set_ALMPOL_bit(alarm_nr) # Set ALMPOL bit of Alarm1 (so the MFP follows the ALM1IF)
        
    if alarm2en and alarm_nr == 2:
        if my_debug:
            print(TAG+f"setting alarm2 for: {t[:5]}, {dow}")
        # ---------------------------------------------------------------
        # SET ALARM2
        # ---------------------------------------------------------------
        mcp.alarm2 = t  # Set alarm2
        # ---------------------------------------------------------------
        
        t_ck = mcp.alarm2[:6]  # check result
        if my_debug:
            print(TAG+f"check: alarm2 is set for: {t_ck}")
        state.alarm2 = t_ck
        state.alarm2_set = True
        mcp._clr_ALMxIF_bit(alarm_nr)     # Clear the interrupt of alarm1
        mcp._set_ALMxMSK_bits(alarm_nr,1) # Set the alarm1 mask bits for a minutes match
        if not mcp._read_ALM_POL_IF_MSK_bits(alarm_nr, state.POL):
            mcp._set_ALMPOL_bit(alarm_nr) # Set ALMPOL bit of alarm1 (so the MFP follows the ALM1IF)

def clr_alarm(state, alarm_nr=None):
    TAG = tag_adj(state, "clr_alarm(): ")
    if alarm_nr is None:
        return
    
    num_regs = 8

    eal = (0,)*num_regs

    if alarm_nr in [1, 2]:
        if alarm_nr == 1:
            mcp.alarm1 = eal  # clear alarm1 datetime stamp
            mcp._clr_ALMxIF_bit(1) # clear alarm1 Interrupt Flag bit
            state.alarm1_set = False
            state.alarm1 = eal
            mcp.alarm_enable(alarm_nr, False)  # Disable alarm1
            if my_debug:
                print(TAG+f"state.alarm1: {state.alarm1[:num_regs]}")
            ck = mcp.alarm1[:6]
        elif alarm_nr == 2:
            mcp.alarm2 = eal    # clear alarm2 datetime stamp
            mcp._clr_ALMxIF_bit(2) # clear alarm2 Interrupt Flag bit
            state.alarm2_set = False
            state.alarm2 = eal
            mcp.alarm_enable(alarm_nr, False)  # Disable alarm2
            if my_debug:
                print(TAG+f"state.alarm2: {state.alarm2[:num_regs]}")
            ck = mcp.alarm2[:6]
        if my_debug:
            print(TAG+f"alarm{alarm_nr}, check: {ck}")

def pol_alarm_int(state):
    TAG = tag_adj(state, "pol_alarm_int(): ")
    t_ck = None
    alarm1en = False
    alarm2en = False
    alm1msk_bits = None
    alm2msk_bits = None

    for _ in range(2):
        if _ == 0:
            alarm1en = True if mcp.alarm_is_enabled(1) else False
        if _ == 1:
            alarm2en = True if mcp.alarm_is_enabled(2) else False

    if alarm1en:
        if my_debug:
            print(TAG+"alarm1 is enabled")
        #t_ck = mcp.alarm1[:6]  # check result
        t_ck = state.alarm1[:6]
        if my_debug:
            print(TAG+f"alarm1 is set for: {t_ck}")
        state.alarm1_int = True if mcp._read_ALM_POL_IF_MSK_bits(1, state.IF) else False
        if state.alarm1_int:
            alm1if_bit = mcp._read_ALM_POL_IF_MSK_bits(1, state.IF)
            if my_debug:
                print(TAG+"we have an interrupt from alarm1")
                print(TAG+"alarm1 IF bit: {:b}".format(alm1if_bit))
                alm1msk_bits = mcp._read_ALM_POL_IF_MSK_bits(1, state.MSK)
                show_alm_match_type(alm1msk_bits)
            ck_rtc_mfp_int(state)

    if alarm2en:
        if my_debug:
            print(TAG+"alarm2 is enabled")
        #t_ck = mcp.alarm2[:6]  # check result
        t_ck = state.alarm2[:6]
        if my_debug:
            print(TAG+f"alarm2 is set for: {t_ck}")
        state.alarm2_int = True if mcp._read_ALM_POL_IF_MSK_bits(2, state.IF) else False
        if state.alarm2_int:
            alm2if_bit = mcp._read_ALM_POL_IF_MSK_bits(2, state.IF)
            if my_debug:
                print(TAG+"we have an interrupt from alarm2")
                print(TAG+"alarm2 IF bit: {:b}".format(alm2if_bit))
                alm2msk_bits = mcp._read_ALM_POL_IF_MSK_bits(2, state.MSK)
                show_alm_match_type(alm2msk_bits)
            ck_rtc_mfp_int(state)

# check the RTC interrupt line (RTC io4 to FeatherS3 io33)
def ck_rtc_mfp_int(state):
    TAG = tag_adj(state, "ck_rtc_mfp_int(): ")
    v = rtc_mfp_int.value()
    if my_debug:
        print(TAG+f"rtc_mfp_int.value: {v}")
    s = "High" if v else "Low "
    if my_debug:
        print(TAG+f"rtc interrupt line value: {s}")
    if v in [0, 1]:
        state.mfp = True if v == 1 else False

# Called from function: pol_alarm_int(state)
def show_alm_match_type(msk=None):
    TAG = tag_adj(state, "show_alm_match_type(): ")
    if msk is None:
        return
    if msk >= 0 and msk <= 7:
        print(TAG+f"match type: {mcp._match_lst[msk]}")


def show_mfp_output_mode_status(stete):
    if state.loop_nr < 3:
        return
    print()
    print("MCP7940 MFP output mode:")
    s1 = "+--------+--------+--------+--------------------------+"
    s2 = "| SQWEN  | ALM0EN | ALM1EN |          Mode            |"
    aio = "Alarm Interruput output "
    sqwen =  mcp._read_SQWEN_bit()
    alm1en = mcp.alarm_is_enabled(1)
    alm2en = mcp.alarm_is_enabled(2)

    if not sqwen:
        if not alm1en:
            if not alm2en:  # 0 0 0
                mode = "Gen purpose output      "
            elif alm2en:    # 0 0 1
                mode = aio
        elif alm1en:
            if not alm2en:  # 0 1 0
                mode = aio
            elif alm2en:    # 0 1 1
                mode = aio
    elif sqwen:             # 1 x x
        mode = "Square Wave Clock Output"
    else:
        mode = "Unknwon                 "

    s3= "|   {:d}    |   {:d}    |   {:d}    | {:s} |".format(sqwen, alm1en, alm2en, mode)
    print(s1)
    print(s2)
    print(s1)
    print(s3)
    print(s1)
    print("See: MCP7940N datasheet DS20005010H-page 25")
    print()


def show_alarm_output_truth_table(state, alarm_nr=None):
    TAG = tag_adj(state, "show_alarm_output_truth_table(): ")
    if alarm_nr is None:
        return
    if not alarm_nr in [1, 2]:
        return

    s_ALMxIF = "ALM"+str(alarm_nr)+"IF"

    print()
    print(f"Single alarm output truth table for alarm{alarm_nr}:")
    s1 = "+--------+---------+-------+----------------------------------+"
    s2 = "| ALMPOL |  {:6s} |  MFP  |            Match type            |".format(s_ALMxIF)
    
    alarm_POL = 0
    alarm_IF = 0
    alarm_MSK = 0
    for _ in range(3):
        itm = mcp._read_ALM_POL_IF_MSK_bits(alarm_nr, _)
        if _ == 0:
            alarm_POL = itm # Read alarm1 or alarm2 ALMPOL bit
        elif _ == 1:
            alarm_IF = itm # Read alarm1 or alarm2 interrupt flag
        elif _ == 2:
            alarm_MSK = itm # Read ALMxMSK bits of alarm1 or alarm2
    if my_debug:
        print(TAG+"ALM{:d}MSK_bits: b\'{:03b}\'".format(alarm_nr, alarm_MSK))
    msk_match = state._match_lst_long[alarm_MSK] # get the match long text equivalent
    mfp = rtc_mfp_int.value() # get the RTC shield MFP interrupt line state

    if my_debug:
        print(f"show_alarm_output_truth_table(): alarm{alarm_nr}_POL: {alarm_POL}, alarm{alarm_nr}_IF: {alarm_IF}, mfp: {mfp}")

    notes1 = "mask bits: \'b{:03b}\' type: {:8s}".format(alarm_MSK, msk_match)
    s3= "|   {:d}    |    {:d}    |   {:d}   | {:24s} |".format(alarm_POL, alarm_IF, mfp, notes1)
    print(s1)
    print(s2)
    print(s1)
    print(s3)
    print(s1)
    print("See: MCP7940N datasheet DS20005010H-page 27")
    print()

def get_ampm(hh):
    ret = " ?"
    if isinstance(hh, int):
        if mcp._is_12hr: # was: if state.dt_str_usa:
            ret = "PM" if mcp._is_PM(hh) == 1 else "AM"
        else:
            ret = str(hh)
    return ret

def show_alm_int_status(state):
    TAG = tag_adj(state, "show_alm_int_status(): ")
    match1 = ""
    match2 = ""
    s_sec = "AM/PM" if state.dt_str_usa else "SECOND"
    s1 = "+-------------+----------+-------+-----+------+--------+--------+---------+---------------------+--------------------+"
    s2 = "|  ALARM  Nr  | ENABLED? | MONTH | DAY | HOUR | MINUTE | {:6s} | WEEKDAY | INTERRUPT OCCURRED? | NOTES:             |".format(s_sec)
    
    ae1=mcp.alarm_is_enabled(1)
    ae2=mcp.alarm_is_enabled(2)
    is_12hr = mcp._is_12hr
    
    if my_debug:
        print(TAG+f"alarm1 enabled:{ae1}, alarm2 enabled: {ae2}")

    if ae1:
        alarm1en = "Yes" if ae1 else "No  "
        ts1 = state.alarm1[:6]  # slice off yearday and isdst
        if my_debug:
            print(TAG+f"alarm1 set for: {ts1}")
            
        mo1, dd1, hh1, mi1, ss1, wd1 = ts1
        
        ss1 = get_ampm(hh1)
        
        if is_12hr:
            if hh1 >= 12:
                hh1 -= 12

        match1 = mcp._match_lst[mcp._read_ALM_POL_IF_MSK_bits(1, state.MSK)]
        if match1 == "mm" and not state.dt_str_usa:
            ss1 = None
    if ae2:
        alarm2en = "Yes" if ae2 else "No  "
        ts2 = state.alarm2[:6]  # slice off yearday and isdst
        if my_debug:
            print(TAG+f"alarm2 set for: {ts2}")
            
        mo2, dd2, hh2, mi2, ss2, wd2 = ts2
        
        ss2 = get_ampm(hh2)
        
        if is_12hr:
            if hh2 >= 12:
                hh2 -= 12
       
        match2 = mcp._match_lst[mcp._read_ALM_POL_IF_MSK_bits(2, state.MSK)]
        if match2 == "mm" and not state.dt_str_usa:
            ss2 = None

    tm_current = mcp.mcptime # Get current datetime stamp from the External UM MCP7940 RTC shield
    if my_debug:
        print(TAG+f"mcp.mcptime: {tm_current}")

    num_registers = len(tm_current)
    if my_debug:
        print(TAG+f"num_registers: {num_registers}")
    
    if num_registers == 7:
        _, c_mo, c_dd, c_hh, c_mi, c_ss, c_wd = tm_current # Discard year
    elif num_registers == 9:
        _, c_mo, c_dd, c_hh, c_mi, c_ss, c_wd, _, _ = tm_current  # Discard year, yearday and isdst
    elif num_registers == 11:
        _, c_mo, c_dd, c_hh, c_mi, c_ss, c_wd, _, _, _, _ = tm_current  # Discard year, yearday and isdst, is_12hr, is_PM
    
    c_ss = get_ampm(c_hh)
    
    if is_12hr:
            if c_hh >= 12:
                c_hh -= 12
    
    # v = "Yes " if rtc_mfp_int.value else "No  "
    v = "Yes " if state.mfp else "No  "

    s3 = "|      {:s}      |    {:s}     |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:s}                   | {:18s} |". \
        format("X","X", c_mo, c_dd, c_hh, c_mi, c_ss, mcp.DOW[c_wd][:3],"X","CURRENT DATETIME")

    if ae1:
        if ss1 is None: # We don't display seconds if we do an alarm match on minutes
            s4 = "|      {:d}      |   {:s}    |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:3s}                | {:18s} |". \
            format(1, alarm1en, mo1, dd1, hh1, mi1, " X", mcp.DOW[wd1][:3], v, "ALARM1 SET FOR")
        else:
            s4 = "|      {:d}      |   {:s}    |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:3s}                | {:18s} |". \
            format(1, alarm1en, mo1, dd1, hh1, mi1, ss1, mcp.DOW[wd1][:3], v, "ALARM1 SET FOR")

    if ae2:
        if ss2 is None: # We don't display seconds if we do an alarm match on minutes
            s5 = "|      {:d}      |   {:s}    |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:3s}                | {:18s} |". \
            format(2, alarm2en, mo2, dd2, hh2, mi2, " X", mcp.DOW[wd2][:3], v, "ALARM2 SET FOR")
        else:
            s5 = "|      {:d}      |   {:s}    |  {:2d}   |  {:2d} |  {:2d}  |   {:2d}   |   {:2s}   |   {:s}   | {:3s}                | {:18s} |". \
            format(2, alarm2en, mo2, dd2, hh2, mi2, ss2, mcp.DOW[wd2][:3], v, "ALARM2 SET FOR")

    nxt_int = mi1 if ae1 else mi2 if ae2 else -1 # Next interrupt expected at minute:
    
    print()
    print("Alarm interrupt status:")
    if match1 == "mm" or match2 == "mm" and nxt_int != -1:
        print(f"Expect next alarm at minute: {nxt_int}")
    print(s1)
    print(s2)
    print(s1)
    print(s3)
    print(s1)
    if ae1:
        print(s4)  # Print only enabled alarm
    print(s1)
    if ae2:
        print(s5) # idem
        print(s1)

dt_name_dict = {
    0: "year",
    1: "month",
    2: "dayofmonth",
    3: "hour",
    4: "minute",
    5: "second",
    6: "weekday",
    7: "yearday",
    8: "isdst",
    9: "is_12hr",
    10: "is_PM"
}

def get_dt(state):
    TAG = tag_adj(state,"get_dt(): ")
    dt = ()
    if state.lStart:
        state.lStart = False
        while True:
            dt = mcp.mcptime
            le = len(dt)
            if le < 2:
                if not my_debug:
                    print(TAG+f"call to mcp.mcptime() failed")
                return (0,)
            if dt[state.tm_sec] == 0: # align for 0 seconds (only at startup)
                break
    else:
        dt = mcp.mcptime
        le = len(dt)
        if le < 2:
            if not my_debug:
                print(TAG+f"call to mcp.mcptime() failed")
            return (0,)
    state.MCP_dt = dt
    if my_debug:
        print(TAG+f"returning value: dt: {dt}")
    return dt

def get_dt_S(state):
    TAG = tag_adj(state,"get_dt_S(): ")
    if my_debug:
        print(TAG+f"state.UTC_OFFSET: {state.UTC_OFFSET}")
    lcl_dt = utime.localtime(utime.time()) # + state.UTC_OFFSET)
    lcl_dt_hh = lcl_dt[state.tm_hour]
    tm = mcp.mcptime
    if len(tm) < 2:
        return ""
    if my_debug:
        print(TAG+f"tm: {tm}, len(tm): {len(tm)}")
    if len(tm) < 2:
        print(TAG+"Reading the MCP7940.time() failed")
        return
    mcp_dt = list(tm)  # create a list (which is mutable)
    mcp_dt_hh = mcp_dt[state.tm_hour]
    yrday = mcp.yearday()
    is_12hr = mcp._is_12hr
    
    if is_12hr:
        if mcp_dt_hh >= 12:
            mcp_dt_hh -= 12
    
    if my_debug:
        print(TAG+f"is_12hr: {is_12hr}, lcl_dt_hh: {lcl_dt_hh}, mcp_dt_hh: {mcp_dt_hh} ")
        # print(TAG+f"utime.localtime(utime.time() + state.UTC_OFFSET (= lcl_dt): {lcl_dt})")
        print(TAG+f"utime.localtime(utime.time()) (= lcl_dt): {lcl_dt})")

    s_PM = get_ampm( mcp_dt[state.tm_hour])  # don't use mcp_dt_hh because it has been changed

    if my_debug:
        print(TAG+f"mcp.mcptime: {mcp_dt}")
    try:
        dt_s = "{:3s} {:02d} {:4d}".format(state.month_dict[mcp_dt[state.tm_mon]], mcp_dt[state.tm_mday], mcp_dt[state.tm_year])
        tm_s = "{:d}:{:02d}:{:02d} {:2s}".format(mcp_dt_hh, mcp_dt[state.tm_min], mcp_dt[state.tm_sec], s_PM)
        ret = "{} {}, {}. Day of year: {:>3d}".format(mcp.weekday_S(), dt_s, tm_s, yrday)
        wd = mcp.weekday_S()
        yd = str(yrday)
    except KeyError as e:
        print(TAG+f"Error: {e}")
        ret = ""
        wd = ""
        yd = ""
    if my_debug:
        print(TAG+f"return value: {ret}")
    if use_sh1107:
        msg = ["Loop: "+str(state.loop_nr)+" of "+str(state.max_loop_nr), "", wd, " ", dt_s, " ", tm_s, " ", "yearday: "+yd ]
        pr_msg(state, msg)
    return ret

    
def clr_scrn():
    if use_sh1107:
        #display.sleep(False)
        display.fill(0)
        display.show()
        
def pr_msg(state, msg_lst=None):
    # TAG = tag_adj(state, "pr_msg(): ")
    if msg_lst is None:
        msg_lst = ["pr_msg", "test message", "param rcvd:", "None"]
    le = len(msg_lst)
    max_lines = 9
    nr_lines = max_lines if le >= max_lines else le

    if use_sh1107:
        display.sleep(False)
        display.fill(0)
        display.show()
        utime.sleep(0.5)
        row = 0
        row_step = 10
        if le > 0:
            for i in range(nr_lines):
                #            text        x  y    c
                display.text(msg_lst[i], 0, row, 1)
                row += row_step
                if row >= 100:
                    row = 0
            display.show()
            utime.sleep(3)

    #if use_sh1107:
    #    display.sleep(True)
     
    # Print only to REPL
    print()
    for i in range(nr_lines):
        print(f"{msg_lst[i]}")
    print()

def tag_adj(state,t):
    if use_TAG:
        le = 0
        spc = 0
        ret = t

        if isinstance(t, str):
            le = len(t)
        if le >0:
            spc = state.tag_le_max - le
            #print(f"spc= {spc}")
            ret = ""+t+"{0:>{1:d}s}".format("",spc)
            #print(f"s=\'{s}\'")
        return ret
    return ""

def setup(state):
    global config, wifi
    TAG = tag_adj(state, "setup(): ")
    s_mcp = "MCP7940"
    
    fn = 'dst_data.json'
    
    id = list(unique_id())
    s_id = ""
    le = len(id)
    for _ in range(le):
        if _ == le-1:
            s_id += "{:02x}".format(id[_])
        else:
            s_id += "{:02x}:".format(id[_])
    
    state.board_id = s_id   
    print(TAG+f"board unique_id: {state.board_id}")
    
    if state.board_id == s_id:
        try:
            state.curr_color_set = "BLK"
            neopixel_color(state, state.curr_color_set)
            
            usb_pwr = feathers3.get_vbus_present()
            if usb_pwr:
                s_pwr ="USB"
            else:
                s_pwr ="battery"
            msg = ["we are on:","", s_pwr+" power"]
            
            pr_msg(state, msg)
            # Turn on the power to the NeoPixel
            feathers3.set_ldo2_power(True)
            
            state.neopixel_brightness = 0.005

        except ValueError:
            pass
    
    wlan = network.WLAN(network.STA_IF)
    state.wlan = wlan
    
    do_connect(state)
    
    if wlan.isconnected():
        set_time(state)  # call at start  
        gc.collect()

    state.MCP_dt = mcp.mcptime
    state.SYS_dt = utime.localtime()
    state.SRAM_dt = None  #see setup()
    
    if my_debug:
        print(TAG+f"Current ntp host: \'{ntp.get_host()}\'")

    is_started = mcp._is_started()
    if is_started > -1:
        if not is_started:
            if not my_debug:
                print(TAG+f"{s_mcp} not started yet...")
            mcp.start()
            is_started2 = mcp._is_started()
            if is_started2 > -1:
                if not my_debug:
                    print(TAG+f"{s_mcp} now started")
            else:
                print(TAG+f"failed to start {s_mcp}")
        else:
            if my_debug:
                print(TAG+f"{s_mcp} is running")
            
    pf = mcp.has_pwr_failed()
    if pf > -1:
        spf = "Yes" if pf else "No"
        print(TAG+f"MCP7940 power failure occurred? {spf}")
        if pf:
            mcp.clr_pwr_fail_bit()
            pwrup = mcp.pwr_updn_dt(True)
            pwrdn = mcp.pwr_updn_dt(False)
            print(TAG+f"power up   timestamp: {pwrup}")
            print(TAG+f"power down timestamp: {pwrdn}")
    else:
        print(TAG+"Unable to read the pwr failed bit")
        
    bbe = mcp._is_battery_backup_enabled()
    if bbe > -1:
        s = "" if bbe else " not"
        print(TAG+f"{s_mcp} backup battery is{s} enabled")

        if not bbe:
            print(TAG+"going to enable")
            mcp.battery_backup_enable(True)
            bbe = mcp._is_battery_backup_enabled()
            if bbe:
                print(TAG+"backup battery is now enabled")
            else:
                print(TAG+"failed to enable backup battery")
    else:
        print(TAG+"Unable to read the battery backup enable bit")
    
    if state.dt_str_usa == True:
        print(TAG+"setting MCP7940 for 12hr time format")
        ret = mcp.set_s11_12hr(state.dt_str_usa) # Set for time format USA (12 hours & AM/PM
        if ret > -1:
            # Check the value set
            is12hr = mcp._is_12hr
            config["is_12hr"] = is12hr  # save to json
            save_config()
        else:
            print(TAG+"setting mcp._is_12hr failed")
        
        print(TAG+f"check: is12hr: {is12hr}")
      
    if my_debug:
        upd_SRAM(state)

    if my_debug:
        print(TAG+f"MCP7940_RTC datetime year read from SRAM = {state.SRAM_dt}")   # SRAM_dt_dict[0][dt_name_dict[0]] )

    if not mcp._is_started():
        if my_debug:
            print(TAG+"Going to start the RTC\'s MCP oscillator")
        mcp.start() # Start MCP oscillator
        is_started = mcp._is_started()
        if is_started > -1:
            if is_started:
                print(TAG+"RTC\'s ocillator is running now")
            else:
                print(TAG+"failed to start the oscillator of the MCP7940 RTC")
        else:
            print(TAG+"unable to read the start bit")

    
    print(TAG+f"Microcontroller (utime.localtime()) year = {state.SYS_dt[state.tm_year]}")
    print(TAG+f"MCP7940_RTC datetime year                = {state.MCP_dt[state.tm_year]}")
    print(TAG+f"utime.localtime() result: {state.SYS_dt}") #, type: {type(state.SYS_dt)}")       
    print(TAG+f"MCP7940 RTC set to: {state.MCP_dt}") #, type: {type(state.MCP_dt)}")
    
    if not my_debug:
        print(TAG+"start setting up MCP7940")
    alarm_nr = 1
    mcp._clr_SQWEN_bit()        # Clear the Square Wave Enable bit
    print(TAG+f"check: alarm{alarm_nr} ALMPOL_bit: {mcp._read_ALM_POL_IF_MSK_bits(1, state.POL)}")
    mcp._clr_ALMxIF_bit(alarm_nr)      # Clear the interrupt of alarm1
    mcp._set_ALMxMSK_bits(alarm_nr,1)  # Set the alarm1 mask bits for a minutes match
    mcp._set_ALMPOL_bit(alarm_nr)      # Set ALMPOL bit of Alarm1 (so the MFP follows the ALM1IF)
    state.alarm1_int = False
    mcp.alarm_enable(alarm_nr, True)   # Enable alarm1
    if not my_debug:
        print(TAG+"...")
    
    alarm_nr = 2
    print(TAG+f"check: alarm{alarm_nr} ALMPOL_bit: {mcp._read_ALM_POL_IF_MSK_bits(2, state.POL)}")
    mcp._clr_ALMxIF_bit(alarm_nr)      # Clear the interrupt of alarm2
    mcp._set_ALMxMSK_bits(alarm_nr,1)  # Set the alarm2 mask bits for a minutes match
    mcp._set_ALMPOL_bit(alarm_nr)      # ALMPOL bit of Alarm2 (so the MFP follows the ALM2IF)
    state.alarm2_int = False
    mcp.alarm_enable(alarm_nr, False)  # Disable alarm2

    state.mfp = True if rtc_mfp_int.value == 1 else False

    if not my_debug:
        print(TAG+"finished setting up MCP7940")
    # ret = prepare_alm_int(state)  # Prepare for alarm interrupt polling

def main():
    global state
    state = State()
    TAG = tag_adj(state, "main(): ")
    read_fm_config(state)
    setup(state)
    t = utime.localtime()  
    o_hour = t[state.tm_hour] # Set hour for set_time(state) call interval
    o_sec = t[state.tm_sec]
    t_start = utime.ticks_ms()
    state.loop_nr = 1
    print("\n"+TAG+"Test: saving and reading datetime data to/from MCP7940 SRAM")
    led.off()
    mins_start = 0
    mins_curr = 0
    if use_sh1107:
        clr_scrn()
    alarm_start = True
    
    while True:
        try:
            t = utime.localtime()
            #     yr,   mo, dd, hh, mm, ss, wd, yd, dst
            #t = (2022, 10, 30, 2, 10, 0,  0,  201, -1)  # For testing purposes
            if o_hour != t[state.tm_hour]:
                o_hour = t[state.tm_hour] # remember current hour
                set_time(state)
                gc.collect()
            if o_sec != t[state.tm_sec]:
                o_sec = t[state.tm_sec] # remember current second
                led.on()
                dst = "Yes" if is_dst() else "No"
                t2 = "\nLocal date/time: {} {}-{:02d}-{:02d}, {:02d}:{:02d}:{:02d}, day of the year: {}. DST: {}".format(state.mRTC_DOW[t[state.tm_wday]], t[state.tm_year],
                    t[state.tm_mon], t[state.tm_mday], t[state.tm_hour], t[state.tm_min], t[state.tm_sec], t[state.tm_yday], dst)
                print(t2)
            rd_sram = True
            if not rd_sram:
                print(TAG+"\nTo see a printout of SRAM ? Set flag \'rd_sram\' to True")
            curr_dt = mcp.mcptime # get the MCP7940 timekeeping data
            print(TAG+f"Current MCP7940 RTC datetime: {get_dt_S(state)}")
            res = upd_SRAM(state)
            if res == -1:
                if not my_debug:
                    print(TAG+f"call to upd_SRAM() failed")
            led.off()
        except KeyboardInterrupt:
            print("", end='\n')
            raise SystemExit
    
        utime.sleep(3)

        print("", end='\n')
        #print("Waiting 10 secs so you can copy REPL output")
        #utime.sleep(10)
        while True:
             # ------------------------------------------------------------------------------------------------
            if alarm_start:
                alarm_nr = 1
                clr_alarm(state, alarm_nr)
                state.alarm1_set = False
                # mcp._set_ALMxMSK_bits(alarm_nr, 1)  # Set Alarm1 Mask bits to have Alarm Minutes match
                if not state.alarm1_set:
                    mcp.alarm_enable(alarm_nr, True)   # Enable alarm1
                    set_alarm(state, alarm_nr, 2) # Set alarm1 for time now + 2 minutes
                    state.alarm1_set = True
                    alarm_start = False
                #pol_alarm_int(state)  # Check alarm interrupt
            ck_rtc_mfp_int(state)
            show_mfp_output_mode_status(state)
            if state.loop_nr >= 3:  # Only perform this
                show_alarm_output_truth_table(state, 1) # Show alarm output truth table for alarm1
                show_alm_int_status(state)
                state.alarm1_int = True if mcp._read_ALM_POL_IF_MSK_bits(1, state.IF) else False
                if state.alarm1_int:
                    interrupt_handler(state)
            # pol_alarm_int(state)  # Check alarm interrupt
            """
            if state.mfp:  # We have an interrupt!
                print(TAG+"RING RING RING we have an interrupt from the RTC shield!")
                alarm_blink(state)
                mcp._clr_ALMxIF_bit(1) # Clear the interrupt
                state.mfp = False
                raise KeyboardInterrupt
            """
            # -------------------------------------------------------------------------------------------------
            t_current = utime.ticks_ms()
            t_elapsed = t_current - t_start      
            if t_elapsed >= 1000: # was: 10000:
                print("\n"+TAG+f"loop_nr: {state.loop_nr}, t_elapsed: {t_elapsed} mSec")
                t_start = t_current
                #dt = get_dt(state)  # Get datetime
                #if len(dt) >= 2:
                #    print(TAG+f"loop_nr: {loop_nr}, dt: {dt}")
                if not my_debug:
                    print(TAG+f"Current MCP7940 RTC datetime: {get_dt_S(state)}")
                print()
                state.loop_nr += 1
                if state.loop_nr > state.max_loop_nr:
                    neopixel_color(state, "BLK")
                    print(TAG+f"Nr of runs: {state.loop_nr-1}. Exiting...") #  "You now can make a copy of the REPL output")
                    if use_sh1107:
                        clr_scrn()
                        msg = ["That\'s all folks!",""]
                        pr_msg(state, msg)
                    gc.collect()
                    sys.exit() # stop to give user oppertunity to copy REPL output.

if __name__ == '__main__':
    main()
