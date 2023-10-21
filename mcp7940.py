#
# Downloaded from: https://github.com/tinypico/micropython-mcp7940/blob/master/mcp7940.py
# On 2022-02-27
# Following are modifications by @Paulskpt (GitHub)
# Added global debug flag `my_debug`
# In class MCCP7940, the following functions added by @Paulskpt:
# - set_12hr()
# - is_12hr()
# - set_PM()
# - is_PM()
# - weekday_N()
# - weekday_S()
# - yearday()
# - is_pwr_failur()
# - clr_pwr_failure_bit()
# - _clr_SQWEN_bit()
# - _read_SQWEN_bit()
# - _set_ALMPOL_bit()
# - _clr_ALMPOL_bit()
# - _read_ALMPOL_bit()
# - _read_ALMxIF_bit()
# - _clr_ALMxIF_bit()
# - _read_ALMxMSK_bits()
# - _set_ALMxMSK_bits()
# - pwr_updn_dt()
# - clr_SRAM()
# - show_SRAM()
# - write_to_SRAM()
# - read_fm_SRAM()
#
# Added dictionaries: DOW and DOM
# Added self._match_lst
#
# Functions modified by @PaulskPt:
# - start()
# - stop()
# - mcptime()  setter
# - _mcpget_time()
#
# In functions start() and stop() added functionality to wait for the osc_run_bit to change (See the MC=7940  datasheet DS20005010H-page 15, Note 2)
# For this in function mcptime() (Setter) I added calls to stop() and start() before and after writing a new time to the MC7940 RTC.
# Be aware when setting an alarm time one loses the state ALMPOL bit, the ALMxIF bit and the three ALMxMSK bits. 
# Thus when setting an alarm make sure to set ALMPOL, ALMx1F and ALMxMSK for alarm1 and/or alarm2 in your code.py script. 
# See the example in function set_alarm() in my code.py example.
# For the sake of readability: replaced index values like [0] ...[6] with [RTCSEC] ... [RTCYEAR]
#
# About clearing the alarm Interrupt Flag bit (ALMxIF). 
# See MCP7940 datasheet  DS20005010H-page 23, note 2
# See also paragraph 5.4.1 on page 21
# Writing to the ALMxWKDAY register will always clear the ALMxIF bit.
# This is what we do in function _clr_ALMxIF_bit().
#
from micropython import const
import time

my_debug = False

class MCP7940:
    """
        Example usage:

            # Read time
            mcp = MCP7940(i2c)
            time = mcp.mcptime # Read time from MCP7940
            is_leap_year = mcp.is_leap_year() # Is the year in the MCP7940 a leap year?

            # Set time
            ntptime.settime() # Set system time from NTP
            mcp.mcptime = time.localtime() # Set the MCP7940 with the system time
    """
    
    ADDRESS = const(0x6F)  # '11001111'
    RTCSEC = 0x00 # RTC seconds register
    ST = 7  # Status bit
    RTCWKDAY = 0x03  # RTC Weekday register
    VBATEN = 3  # External battery backup supply enable bit
    
    """ Begin of definitions added by @PaulskPt """
    CLS_NAME = "MCP7940"
    CONTROL_BYTE = 0xde  # '1101 1110'
    CONTROL_REGISTER = 0x00  # control register on the MCP7940
    RTCC_CONTROL_REGISTER = 0X07
    REGISTER_ALARM0  = 0x0A
    REGISTER_ALM0WKDAY = 0x0D
    REGISTER_ALARM1  = 0x11
    REGISTER_ALM1WKDAY = 0x14
    REGISTER_PWR_FAIL = 0x18

    SRAM_START_ADDRESS = 0x20  # a SRAM space on the MCP7940
    
    # MCP7940 registers

    RTCMIN = 0x01
    RTCHOUR = 0x02

    RTCDATE = 0x04
    RTCMTH = 0x05
    RTCYEAR = 0x06
    PWRDN_ADDRESS = 0X18
    PWRUP_ADDRESS = 0x1C
    PWRMIN = 0x00 # reg 0x1C
    PWRHOUR = 0x01 # reg 0x1D
    PWRDATE = 0x02 # reg 0x1E
    PWRMTH = 0x03 # reg 0x1F
    PWRFAIL_BIT = 4
    OSCRUN_BIT = 5
    ALARM0EN_BIT = 4 
    ALARM1EN_BIT = 5
    SQWEN_BIT = 6
    ALMPOL_BIT = 7
    ALMxIF_BIT = 3
 
    
    bits_dict = {3: "VBATEN",
                 4: "FAIL",
                 7: "STATUS"}
    
    # Definitions added by @PaulskPt
    TIME_AND_DATE_START = 0X00
    PWR_FAIL_REG = 0X03
    TIME_AND_DATE_END = 0X06
    CONFIG_START = 0X07
    CONFIG_END = 0X09
    ALARM1_START = 0X0A
    ALARM1_END = 0X10
    ALARM2_START = 0X11
    ALARM2_END = 0X18
    POWER_FAIL_TIMESTAMP_START = 0X18
    POWER_FAIL_TIMESTAMP_END = 0X1F
    SRAM_START = 0X20  # 64 Bytes
    SRAM_END = 0X5F
    
    
    """ Dictionary added by @Paulskpt. See weekday_S() """
    DOW = { 0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday" }
    
    DOM = { 1:31,
            2:28,
            3:31,
            4:30,
            5:31,
            6:30,
            7:31,
            8:31,
            9:30,
            10:31,
            11:30,
            12:31}
    
    """ End of definitions added by @PaulskPt """

    """ Function modified by @Paulskpt """
    def __init__(self, i2c, status=True, battery_enabled=True):
        self._i2c = i2c
        # lines added by @PaulskPt
        self._match_lst = ["ss", "mm", "hh", "dow", "dd", "res", "res", "all"]
        self._is_12hr = -1 # Set by calling script. Default -1 to indicate it is not yet set
        self.time_is_set = False
        self.last_time_set = ()
        self.sbf = "calling self._set_bit() failed"
        self.rbf = "calling self._read_bit() failed"
        self.gtf = "calling self._mcpget_time() failed"
        
    def has_pwr_failed(self):
        ret = True if self._read_bit(MCP7940.PWR_FAIL_REG, MCP7940.PWRFAIL_BIT) else False
        if ret == -1:
            if my_debug:
                print("reading power fail bit failed")
        return ret
    
    """ Function modified by @Paulskpt """
    def clr_pwr_fail_bit(self):
        TAG = MCP7940.CLS_NAME+".clr_pwr_fail_bit(): "
        ret = self._set_bit(MCP7940.PWR_FAIL_REG, MCP7940.PWRFAIL_BIT, 0)
        if ret == -1:
            if my_debug:
                print(TAG+self.sbf)
        return ret
    
    # Function loops until the oscillator run bit becomes logical '1'
    """ Function modified by @Paulskpt """
    def start(self):
        TAG = MCP7940.CLS_NAME+".start(): "
        ads = 0x3
        osc_run_bit = 0
        ret = self._set_bit(MCP7940.RTCSEC, MCP7940.ST, 1)
        if ret == -1:
            print(TAG+self.sbf)
            return ret
        while True:
            osc_run_bit = self._read_bit(ads, MCP7940.OSCRUN_BIT)
            if osc_run_bit == -1:
                if my_debug:
                    print(TAG+self.rbf)
                break
            #if my_debug:
            #    print(f"MCP7940.start(): osc_run_bit: {osc_run_bit}")
            if osc_run_bit:
                break
        return osc_run_bit
    
    # Function loops until the oscillator run bit becomes logical '0'
    """ Function modified by @Paulskpt """
    def stop(self):
        TAG = MCP7940.CLS_NAME+".stop(): "
        ads = 0x3
        osc_run_bit = 0
        ret = self._set_bit(MCP7940.RTCSEC, MCP7940.ST, 0)
        if ret == -1:
            print(TAG+self.sbf)
            return
        while True:
            osc_run_bit = self._read_bit(ads, MCP7940.OSCRUN_BIT)
            if osc_run_bit == -1:
                if my_debug:
                    print(TAG+self.rbf)
                break
            #if my_debug:
            #    print(f"MCP7940.stop(): osc_run_bit: {osc_run_bit}")
            if not osc_run_bit:
                break   
        return osc_run_bit
    
    """ Function modified by @Paulskpt """
    def is_started(self):
        TAG = MCP7940.CLS_NAME+".is_started(): "
        ret = self._read_bit(MCP7940.RTCSEC, MCP7940.ST)
        if ret == -1:
            if not my_debug:
                print(TAG+self.rbf)
        return ret

    """ Function modified by @Paulskpt """
    def battery_backup_enable(self, enable):
        TAG = MCP7940.CLS_NAME+".battery_backup_enable(): "
        ret = self._set_bit(MCP7940.RTCWKDAY, MCP7940.VBATEN, enable)
        if ret == -1:
            if my_debug:
                print(TAG+self.sbf)
        return ret

    """ Function modified by @Paulskpt """
    def is_battery_backup_enabled(self):
        TAG = MCP7940.CLS_NAME+".is_battery_backup_enabled(): "
        ret = self._read_bit(MCP7940.RTCWKDAY, MCP7940.VBATEN)
        if ret == -1:
            if my_debug:
                print(TAG+self.rbf)
        return ret

    """ Function modified by @Paulskpt """
    def _set_bit(self, register, bit, value):
        """ Set only a single bit in a register. To do so, need to read
            the current state of the register and modify just the one bit.
        """
        TAG = MCP7940.CLS_NAME+"._set_bit(): "
        mask = 1 << bit
        try:
            current = self._i2c.readfrom_mem(MCP7940.ADDRESS, register, 1)
            updated = (current[0] & ~mask) | ((value << bit) & mask)
            self._i2c.writeto_mem(MCP7940.ADDRESS, register, bytes([updated]))
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1  # indicate failure
        return 1  # indicate command execution was successful
       
    """ Function modified by @Paulskpt """
    def _read_bit(self, register, bit):
        TAG = ""
        try:
            register_val = self._i2c.readfrom_mem(MCP7940.ADDRESS, register, 1)
        except OSError as e:
            print(f"Error: {e}")
            return -1
        return (register_val[0] & (1 << bit)) >> bit

    """ Function renamed by @PaulskPt """
    @property
    def mcptime(self):
        return self._mcpget_time()

    """ Function modified by @Paulskpt """
    # Added setting of self.time_is_set flag
    @mcptime.setter
    def mcptime(self, t_in):
        TAG = MCP7940.CLS_NAME+".mcptime() setter: "
        """
            >>> import time
            >>> time.localtime()
            (2019, 6, 3, 13, 12, 44, 0, 154)
            # 1:12:44pm on Monday (0) the 3 Jun 2019 (154th day of the year)
        """
        if my_debug:
            print(TAG+f"param t_in: {t_in}")
        t_in = t_in[:8]  # Slice off too many bytes
        year, month, date, hours, minutes, seconds, weekday, yearday = t_in
        # Reorder
        time_reg = [seconds, minutes, hours, weekday, date, month, year % 100]

        # Add ST (status) bit

        # Add VBATEN (battery enable) bit
        if not my_debug:
            print(
                TAG+"{}/{}/{} {}:{}:{} (day={})".format(
                    time_reg[MCP7940.RTCYEAR],
                    time_reg[MCP7940.RTCMTH],
                    time_reg[MCP7940.RTCDATE],
                    time_reg[MCP7940.RTCHOUR],
                    time_reg[MCP7940.RTCMIN],
                    time_reg[MCP7940.RTCSEC],
                    time_reg[MCP7940.RTCWKDAY],
                )
            )
        
        #print(time_reg)
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F, 0xFF)
        """ Note @Paulskpt zip() is a built-in function of micropython. Works as follows:
            >>> x = [1, 2, 3]
            >>> y = [4, 5, 6]
            >>> zipped = zip(x,y)
            >>> list(zipped)
            [(1, 4), (2, 5), (3, 6)]"""
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        # Note that some fields will be overwritten that are important!
        # fixme!
        bt = bytes(t)
        #if my_debug:
        #    print(TAG+f"t = {t}, bytes(t): {bt}")
            
        ret = self.stop()  # See:  MCP7940 DATASHEET: DS20005010H-page 15
        if ret == -1:
            if not my_debug:
                print(TAG+"calling self.stop() failed")
            return ret
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, MCP7940.CONTROL_REGISTER, bt)
            # We check the result
            time_ck = self._mcpget_time(MCP7940.CONTROL_REGISTER)
            print(TAG+f"time check: {time_ck}")
            if len(time_ck) > 1 and time_ck[0] > 2001:  # we expect a datetime that is > 2001 (= 1)
                self.time_is_set = True  # set flag
                self.last_time_set = time_ck
            #time.sleep(3)
    
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        
        ret = self.start()
        if ret == -1:
            if not my_debug:
                print(TAG+"calling self.start() failed.")
            return ret
    
    # Return state of the self.time_is_set flag
    # Function added to be useful for calling scripts
    # to know if the MCP7940 timekeeping registers already have been set
    """ Function added by @Paulskpt """
    def time_has_set(self):
        return self.time_is_set
        
    # Set the 12hr bit and set self._is_12hr flag if not yet set    
    # See MCP7940 Datasheet DS20005010H-page 17
    """ Function added by @Paulskpt """
    def set_12hr(self, _12hr=None):
        TAG = MCP7940.CLS_NAME+".set_12hr(): "
        if _12hr is None:
            return -1
        if my_debug:
            print(f"MCOP7940.set_12hr(): param _12hr: {_12hr}, type(_12hr): {type(_12hr)}")
        if not isinstance(_12hr, bool):
            return -1
        bit = 6
        reg = MCP7940.RTCHOUR
        value = 1 if _12hr else 0
        if self._is_12hr == -1:  # If not set yet, set it to remember
             self._is_12hr = value # Remember the setting
        if my_debug:
            print(f"MCOP7940.set_12hr(): setting reg: {hex(reg)}, bit {bit}, _12hr {value}")
        ret = self._set_bit(reg, bit, value)
        if ret == -1:
            print(TAG+self.sbf)
        return ret
    
    # See MCP7940 Datasheet DS20005010H-page 17
    """ Function added by @Paulskpt """
    def is_12hr(self):
        TAG = MCP7940.CLS_NAME+".is_12hr(): "
        bit = 6
        ret = 0
        reg = MCP7940.RTCHOUR
        if self._is_12hr == -1:
            ret = self._read_bit(reg, bit)
            if ret == -1:
                if my_debug:
                    print(TAG+self.rbf)
                return ret 
        else: 
            ret = self._is_12hr
        if my_debug:
            print(TAG+f"{ret}")
        return ret
    
    # Set the AMPM bit if the 12hr bit is set
    """ Function added by @Paulskpt """
    def set_PM(self, isPM=None):
        TAG = MCP7940.CLS_NAME+".set_PM(): "
        ret = -1
        ret2 = 0
        if isPM is None:
            return ret
        if not isinstance(isPM, bool):
            return ret
        
        if self._is_12hr > -1:
            is_12hr = self._is_12hr
        else:
            is_12hr = self.is_12hr()
        if is_12hr:
            bit = 5
            reg = MCP7940.RTCHOUR
            value = 1 if isPM else 0
            ret2 = self._set_bit(reg, bit, value)
            if ret2 == -1:
                if my_debug:
                    print(TAG+self.sbf)
            else:
                if my_debug:
                    print(TAG+f"set_PM(): value set: {value}")
        return ret2                    
    
    # Return the AMPM bit is the 12hr bit is set
    # See MCP7940 Datasheet DS20005010H-page 17
    """ Function added by @Paulskpt """
    def is_PM(self):
        TAG = MCP7940.CLS_NAME+".is_PM(): "
        ret = 0
        if self._is_12hr > -1:
            is_12hr = self._is_12hr
        else:
            is_12hr = self.is_12hr()
        if is_12hr:
            bit = 5
            reg = MCP7940.RTCHOUR
            ret = self._read_bit(reg, bit)
            if ret == -1:
                if my_debug:
                    print(TAG+self.rbf)
            if my_debug:
                print(TAG+f"return ret: {ret}")
        return ret
         
    # Enable alarm x
    # See datasheet  DS20005010H-page 26
    """ Function added by @Paulskpt """
    def alarm_enable(self, alarm_nr= None, onoff = False):
        TAG = MCP7940.CLS_NAME+".alarm_enable(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if not isinstance(onoff, bool):
            return -1
        
        reg = MCP7940.RTCC_CONTROL_REGISTER
        
        if alarm_nr == 1:
            bit = MCP7940.ALARM0EN_BIT
        elif alarm_nr == 2:
            bit = MCP7940.ALARM1EN_BIT
        
        value = 1 if onoff else 0
        
        ret = self._set_bit(reg, bit, value)
        if ret == -1:
            print(TAG+self.sbf)
        return ret

    # Check if alarm x is enabled
    """ Function added by @Paulskpt """
    def alarm_is_enabled(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"alarm_is_enabled(): "
        if alarm_nr is None:
            return
        if not alarm_nr in [1, 2]:
            return
        
        reg = MCP7940.RTCC_CONTROL_REGISTER
        
        if alarm_nr == 1:
            bit = MCP7940.ALARM0EN_BIT
        elif alarm_nr == 2:
            bit = MCP7940.ALARM1EN_BIT
        
        ret= self._read_bit(reg, bit)
        if ret == -1:
            print(TAG+self.rbf)
        return ret
    
    @property
    def alarm1(self):
        return self._mcpget_time(start_reg=MCP7940.ALARM1_START)

    """ Function modified by @Paulskpt """
    @alarm1.setter
    def alarm1(self, t):
        TAG = MCP7940.CLS_NAME+"alarm1(): setter "
        _, month, date, hours, minutes, seconds, weekday, _ = t  # Don't need year or yearday
        # Reorder
        time_reg = [seconds, minutes, hours, weekday + 1, date, month]
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F)  # No year field for alarms
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, MCP7940.ALARM1_START, bytes(t))
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        return 1

    """ Function modified by @Paulskpt """
    @property
    def alarm2(self):
        TAG = MCP7940.CLS_NAME+"alarm2(): "
        ret = self._mcpget_time(start_reg=MCP7940.ALARM2_START)
        le = len(ret)
        if len < 2:
            if my_debug:
                print(TAG+self.gtf)
        return ret

    """ Function modified by @Paulskpt """  
    @alarm2.setter
    def alarm2(self, t):
        TAG = MCP7940.CLS_NAME+"alarm2(): setter "
        _, month, date, hours, minutes, seconds, weekday, _ = t  # Don't need year or yearday
        # Reorder
        time_reg = [seconds, minutes, hours, weekday + 1, date, month]
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F)  # No year field for alarms
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, MCP7940.ALARM2_START, bytes(t))
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        return 1

    def bcd_to_int(self, bcd):
        """ Expects a byte encoded with 2x 4bit BCD values. """
        # Alternative using conversions: int(str(hex(bcd))[2:])
        return (bcd & 0xF) + (bcd >> 4) * 10 

    def int_to_bcd(self, i):
        return (i // 10 << 4) + (i % 10)

    """ https://stackoverflow.com/questions/725098/leap-year-calculation """
    def is_leap_year(self, year):
        if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0:
            return True
        return False
    
    # Return the weekday as an integer
    """ Function added by @Paulskpt """
    def weekday_N(self):
        TAG = MCP7940.CLS_NAME+".weekday_N(): "
        if my_debug:
            print(TAG+f"self.mcptime = {self.mcptime}")
        dt = self._mcpget_time()
        le = len(dt)
        if le < 2:
            if my_debug:
                print(TAG+self.gtf)
            return -1
        if my_debug:
            print(TAG+f"dt: {dt}")
        # Year, month, mday, hour, minute, second, weekday, yearday, is_12hr, isPM
        weekday = dt[6]   # slice off not needed values
        #_, _, _, _, _, _, weekday = dt # we don't need: year, month, date, hour, minute, second
        
        if my_debug:
            print(TAG+f"weekday: {weekday}")

        return weekday
    
    # Return the weekday as a string
    """ Function added by @Paulskpt """
    def weekday_S(self):
        TAG = MCP7940.CLS_NAME+".weekday_S(): "
        wd_s = ""
        wd_n = self.weekday_N()
        if wd_n == -1:
            if my_debug:
                print(TAG+"calling self.weekday_N() failed")
                return wd_s
        if wd_n in MCP7940.DOW:
            wd_s = MCP7940.DOW[wd_n]
            if my_debug:
                print(f"weekday_S(): weekday: {wd_s}")
        return wd_s
    
    # Calculate the yearday
    """ Function added by @Paulskpt """
    def yearday(self, dt0=None):
        TAG = MCP7940.CLS_NAME+".yearday(): "
        if my_debug:
            print(TAG+f"param dt0: {dt0}")

        if dt0 is not None: 
            # Prevent 'hang' when called fm self._mcpget_time(),
            # by having self._mcpget_time() furnish dt stamp
            # Slicing [:3]. We need only year, month and mday
            dt = dt0[:3]
        else:
            dt = self._mcpget_time()[:3]
            le = len(dt)
            if le < 2:
                if my_debug:
                    print(TAG+self.gtf)
                    return -1
        ndays = 0
        curr_yr = dt[0]
        curr_mo = dt[1]
        curr_date = dt[2]
        for _ in range(1, curr_mo):
            try:
                ndays += MCP7940.DOM[_]
                if _ == 2 and self.is_leap_year(curr_yr):
                    ndays += 1
            except KeyError:
                pass
        ndays += curr_date
        return ndays
    
    # See datasheet: DS20005010H-page 18
    """ Function added by @Paulskpt """
    def _is_pwr_failure(self):
        TAG = MCP7940.CLS_NAME+"._is_pwr_failure(): "
        reg = MCP7940.RTCWKDAY
        bit = MCP7940.PWRFAIL_BIT
        ret = self._read_bit(reg, bit)
        if ret == -1:
            if my_debug:
                print(TAG+self.rbf)
        else:
            if my_debug:
                print(TAG+f"power failure bit: {ret}")
        return ret
    
    # See datasheet DS20005010H-page 18, Note 2
    """ Function added by @Paulskpt """
    def _clr_pwr_failure_bit(self):
        pwr_bit = bytearray(1)
        pass
    
    # Clear square wave output bit
    """ Function added by @Paulskpt """
    def _clr_SQWEN_bit(self):
        TAG = MCP7940.CLS_NAME+"._clr_SQWEN_bit(): "
        ret = self._set_bit(MCP7940.RTCC_CONTROL_REGISTER, MCP7940.SQWEN_BIT, 0)
        if ret == -1:
            print(TAG+self.sbf)
        return ret
    
    # Read state of the square wave output bit
    """ Function added by @Paulskpt """    
    def _read_SQWEN_bit(self):
        TAG = MCP7940.CLS_NAME+"._read_SWEN_bit(): "
        ret = self._read_bit(MCP7940.RTCC_CONTROL_REGISTER, MCP7940.SQWEN_BIT)
        if ret == -1:
            print(TAG+self.rbf)
        return ret
    
    # Set the alarm pol bit for alarm x
    """ Function added by @Paulskpt """    
    def _set_ALMPOL_bit(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"._set_ALMPOL_bit(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if alarm_nr == 1:
            ads = MCP7940.ALM0WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.ALM1WKDAY
        ret = self._set_bit(ads, MCP7940.ALMPOL_BIT, 1)
        if ret == -1:
            print(TAG+self.sbf)
        if my_debug:
            ck_bit = self._read_ALMPOL_bit(alarm_nr)
            print(TAG+"for alarm{:d}: check: b\'{:b}\'".format(alarm_nr, ck_bit))
        return ret
    
    # Clear the alarm pol bit for alarm x
    """ Function added by @Paulskpt """    
    def _clr_ALMPOL_bit(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"._clr_ALMPOL_bit(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if alarm_nr == 1:
            ads = MCP7940.ALM0WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.ALM1WKDAY
        ret = self._set_bit(ads, MCP7940.ALMPOL_BIT, 0)
        if ret == -1:
            if my_debug:
                print(TAG+self.sbf)
            return ret
        return ret
    
    # read the alarm pol bit for alarm x
    """ Function added by @Paulskpt """
    def _read_ALMPOL_bit(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"._read_ALMPOL_bit(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if alarm_nr == 1:
            ads = MCP7940.ALM0WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.ALM1WKDAY
        ret =  self._read_bit(ads, MCP7940.ALMPOL_BIT)
        if ret == -1:
            if my_debug:
                print(TAG+self.rbf)
            return ret
        else:
            if my_debug:
                print(TAG+"for alarm{:d}, value: b\'{:b}\'".format(alarm_nr, ret))
        return ret
    
    # read the alarm interrupt flag bit for alarm x
    """ Function added by @Paulskpt """
    def _read_ALMxIF_bit(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"._read_ALMxIF_bit(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if alarm_nr == 1:
            ads = MCP7940.ALM0WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.ALM1WKDAY
        ret = self._read_bit(ads, MCP7940.ALMxIF_BIT)
        if ret == -1:
            if my_debug:
                print(TAG+self.rbf)
            return ret
        return ret
    
    # See MCP7940 datasheet  DS20005010H-page 23, note 2
    # Writing to the ALMxWKDAY register will always clear the ALMxIF bit.
    # This is what we do in _clr_ALMxIF_bit() below:
    """ Function added by @Paulskpt """
    def _clr_ALMxIF_bit(self, alarm_nr=None):
        TAG = MCP7940.CLS_NAME+"._clr_ALMxIF_bit():  "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        
        if alarm_nr == 1:
            ads = MCP7940.ALM0WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.ALM1WKDAY

        num_registers = 1
        current = bytearray(num_registers)
        reg_buf = bytearray()
        #reg_buf.append(ads)
        out_buf = bytearray()
        #out_buf.append(ads)

        # Get the current contents of the ALMxWKDAY register
        try:
            #self._i2c.writeto_then_readfrom(MCP7940.ADDRESS, reg_buf, current)
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, current)
            current = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        
        if my_debug:
            print(TAG+"received ALM{:d} weekday value register: lst(current): {}, value: 0x{:0x}, in binary: b\'{:08b}\'". \
                format(alarm_nr, list(current), current[0], current[0]))
        updated = current[0]
        updated = updated & 0xF7 # clear the ALMxIF bit
        out_buf.append(updated)
        
        if my_debug:
            print(TAG+"writing value, hex: 0x{:02x}, binary: b\'{:08b}\'".format(updated, updated) )
            
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, out_buf)  # send data
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1

        reg_buf = bytearray(num_registers)
        ck_buf = bytearray(num_registers)
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, reg_buf)
            ck_buf = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
            le = len(ck_buf)
            if le < 2:
                if my_debug:
                    print(TAG+f"length ckeck weekday value register insufficient")
                    return -1
            ck_if_bit = ck_buf[0]
            ck_if_bit2 = ck_if_bit & 0x7F # isolate b3
            ck_if_bit2 = ck_if_bit2 >> 3  # shift b3 to b0
            if my_debug:
                print(TAG+"check weekday value register rcvd 2nd time: 0x{:02x}, IF bit: hex: 0x{:x}, binary: b\'{:b}\'". \
                    format(ck_if_bit, ck_if_bit2, ck_if_bit2))
                print()
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        return 1
    
    # Read the alarms mask bits for alarm x
    """ Function added by @Paulskpt """
    def _read_ALMxMSK_bits(self, alarm_nr= None):
        TAG = MCP7940.CLS_NAME+"._read_ALMxMSK_bits(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if alarm_nr == 1:
            ads = MCP7940.ALM0WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.ALM1WKDAY
        ret = 0
        num_registers = 1
        reg_buf = bytearray(num_registers)
        current = bytearray(num_registers)
        
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, reg_buf)
            current = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        
        ret = current[0] & 0x70 # isolate bits 6-4
        ret = ret >> 4
        
        if my_debug and ret >= 0 and ret <= 7:
            print(TAG+f"ret: {hex(ret)}, type of match: {self._match_lst[ret]}")
        return ret
    
    # Set the alarm mask (= alarm match) bits for alarm x
    """ Function added by @Paulskpt """
    def _set_ALMxMSK_bits(self, alarm_nr= None, match_type=None):
        TAG = MCP7940.CLS_NAME+"._set_ALMxMSK_bits(): "
        if alarm_nr is None:
            return -1
        if not alarm_nr in [1, 2]:
            return -1
        if match_type is None:
            return -1
        #
        # match type
        # b7 b6 b5 b4 b3 b2 b1 b0
        #  x  0  0  1  x  x  x  x = minute
        # 
        # b'001'  match type
        # b'001'
        # ----- &
        # b'001'  result
        #
        # 
        # b'001'  match type
        # b'010'
        # ----- &
        # b'000'  result
        #
        # current2
        # b'001'  match type
        # b'100'
        # ----- &
        # b'000'  result
        #
        if alarm_nr == 1:
            ads = MCP7940.ALM0WKDAY
        elif alarm_nr == 2:
            ads = MCP7940.ALM1WKDAY
        if match_type >= 0 and match_type <= 7:
            mask = match_type << 4 # minutes
        else:
            mask = 0x00 << 4 # seconds
        
        num_registers = 1
        current = bytearray(num_registers)
        reg_buf = bytearray(num_registers)        
        out_buf = bytearray(num_registers)
        
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, reg_buf)
            current = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
            
        if my_debug:
            print(TAG+"received ALM{:d}MSK_bits: lst(current): {}, value: 0x{:x}, binary: b\'{:b}\'". \
                format(alarm_nr, list(current), current[0], current[0]))
        updated = current[0]
        updated &= 0x8F  # mask bits b6-b4
        updated |= mask  # set for minutes
        out_buf.append(updated)
        if my_debug:
            print(TAG+"writing value: {:02x}, binary: b\'{:b}\'".format(updated, updated))
            new_match_value = updated & 0x70 # isolate bits 6-4
            new_match_value = new_match_value >> 4
            print(TAG+f"= new_match_value: {new_match_value} = {self._match_lst[new_match_value]}")
            
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, out_buf)  # send data
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1

        num_registers = 1
        reg_buf = bytearray(num_registers)
        ck_buf = bytearray(num_registers)
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, reg_buf)
            ck_buf = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
            if my_debug:
                print(TAG+"check: list(ck_buf) {}, ck_buf[0] value: 0x{:02x}, binary: b\'{:08b}\'". \
                    format(list(ck_buf), ck_buf[0], ck_buf[0]))
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1

        if my_debug and match_type >= 0 and match_type <= 7:
            print(TAG+"match type value set: 0x{:02x}, type of match: {:s}". \
                format(match_type, self._match_lst[match_type]))
            print()
        return 1
    
    # Get time for:
    # a) timekeeping registers
    # b) SRAM registers
    # c) alarm1
    # d) alarm2
    # e) power fail
    """ Function renamed and modified by @Paulskpt """
    def _mcpget_time(self, start_reg = 0x00):
        TAG = MCP7940.CLS_NAME+"._mcpget_time(): "
        num_registers = 7 if start_reg == 0x00 else 6
        if my_debug:
            print(TAG+f"param start_reg: {start_reg}, num_registers: {num_registers}")
        time_reg = bytearray(num_registers)
        
        if start_reg == MCP7940.CONTROL_REGISTER:
            r = "control"
        
        elif start_reg == MCP7940.SRAM_START_ADDRESS:
            r = "sram"
        
        elif start_reg == MCP7940.ALARM1_START:
            r = "alarm0"
        
        elif start_reg == MCP7940.ALARM2_START:
            r = "alarm1"
        
        elif start_reg == MCP7940.REGISTER_PWR_FAIL:
            r = "prw_fail"        
        else:
            r = "default"
        
        if my_debug:
            print(TAG+f"using the MCP7940 {r} register")
            print(TAG+f"start_reg: {start_reg} ")
            print(TAG+f"time_reg: {time_reg}")
            print(TAG+f"list(time_reg): {list(time_reg)}")
        
        lStop = False
        # --------------------------------------------------------------------------------------
        # GET THE TIMEKEEPING DATA FROM THE MCP7940 RTC SHIELD
        # --------------------------------------------------------------------------------------
        try:
            time_reg = self._i2c.readfrom_mem(MCP7940.ADDRESS, start_reg, num_registers)  # Reading too much here for alarms
        except OSError as e:
            print(TAG+f"Error: {e}") # . Trying again")
            lStop = True
        finally:
            pass
        # --------------------------------------------------------------------------------------
        if lStop:
            return (0,)
        #             yy    mo    mday  hh    mm    ss    wd
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F, 0xFF)[:num_registers]
        if my_debug:
            print(time_reg)
            print(reg_filter)
        t = [self.bcd_to_int(reg & filt) for reg, filt in zip(time_reg, reg_filter)]
        # Reorder
        if my_debug:
            print(TAG+f"length t: {t}")
        t2 = (t[MCP7940.RTCMTH], t[MCP7940.RTCDATE], t[MCP7940.RTCHOUR], t[MCP7940.RTCMIN], t[MCP7940.RTCSEC], t[MCP7940.RTCWKDAY])
        t3 = (t[MCP7940.RTCYEAR] + 2000,) + t2 if num_registers == 7 else t2
        # now = (2019, 7, 16, 15, 29, 14, 6, 167)  # Sunday 2019/7/16 3:29:14pm (yearday=167)
        # year, month, date, hours, minutes, seconds, weekday, yearday = t
        # time_reg = [seconds, minutes, hours, weekday, date, month, year % 100]

        if my_debug:
            print(TAG+f"returning result t3: {t3}")
        return t3
    
    # Read the datetime stamps of the pwr down / pwr up events
    """ Function added by @Paulskpt """
    def pwr_updn_dt(self, pwr_updn=True): # power up is default
        TAG = MCP7940.CLS_NAME+".get_pwr_up_dt():         "
        reg_buf = bytearray()
        if pwr_updn:
            ads = MCP7940.PWRUP_ADDRESS
        else:
            ads = MCP7940.PWRDN_ADDRESS
   
        num_registers = 4
        time_reg = bytearray(num_registers)
        
        try:
            time_reg = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
            if my_debug:
                s = "up" if pwr_updn else "down"
                print(TAG+f"received MCP7940 power {s} timestamp: {list(time_reg)}")
        except OSError as e:
            print(TAG+f"Error: {e}")
            return (0,)

        #             min   hr    date  wd/month
        reg_filter = (0x7F, 0x3F, 0x3F, 0xFF)[:num_registers]
        if my_debug:
            print(TAG+f"time_reg: {time_reg}")
            print(TAG+f"reg_filter: {reg_filter}")
        t = [self.bcd_to_int(reg & filt) for reg, filt in zip(time_reg, reg_filter)]

        # extract 12/24  flag (True = 12, False = 24)
        _12hr = t[MCP7940.PWRMIN] & 0x40 # (0x40 = 0100 0000)
        _12hr = _12hr >> 6 # move b01000000 to b00000001
        # print(TAG+"{:s} hour format".format("12" if _12hr else "24")))
        # AM/PM flag (True = PM, False = AM)
        _AMPM = t[MCP7940.PWRMIN] & 0x20 # (0x20 = 0010 0000)
        _AMPM = _AMPM >> 5 # move b00100000 to b00000001
        #if _12hr:
        #    print("time: {:s}".format("PM" if _AMPM else "AM"))
        
        # extract weekday:
        wd  = t[MCP7940.PWRMTH] & 0xE0  # (0xE0 = b1110 0000)
        wd = wd >> 5  # move b11100000 to b00000111
        # extract month
        mth = t[MCP7940.PWRMTH] & 0x1F  # (0x1F = b0001 1111)
        if my_debug:
            print(TAG+f"t: {t}")
        # Reorder
        t2 = (mth, t[MCP7940.PWRDATE], t[MCP7940.PWRHOUR], t[MCP7940.PWRMIN], wd)
       
        if _12hr:
            t3 = "PM" if _AMPM else "AM"
            t2 += (t3,) 
        else:
            t3 = ""
            
        if my_debug:
            print(TAG+f"result: {t2} {t3}")

        return t2
    
    # Clear the 64 bytes of SRAM space
    """ Function added by @Paulskpt """
    def clr_SRAM(self):
        TAG = MCP7940.CLS_NAME+".clr_SRAM(): "
        ads = MCP7940.SRAM_START_ADDRESS
        out_buf = bytearray(0x40)
        if my_debug:
            print(TAG+f"length data to write to clear SRAM data: {hex(len(out_buf)-1)}")
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, out_buf)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        return 1
    
    # Print contents of the 64 bytes of SRAM space
    """ Function added by @Paulskpt """
    def show_SRAM(self):
        TAG = MCP7940.CLS_NAME+".show_SRAM(): "
        reg_buf = bytearray(num_registers)
        ads = MCP7940.SRAM_START_ADDRESS
        num_registers = 0x40
        in_buf = bytearray(num_registers) # 0x5F-0x20+1)
        try:   
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, reg_buf)
            in_buf = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        
        print(TAG+"Contents of SRAM:")
        le = len(in_buf)
        for _ in range(le):
            if _ % 10 == 0:
                if _ > 0:
                    print()
            if _ == le-1:
                s = ""
            else:
                s = ", "
            print("{:3d}{:s}".format(in_buf[_], s), end='')
        print()
        return 1

    # Write datetime stamp to SRAM
    """ Function added by @Paulskpt """  
    def write_to_SRAM(self, dt):
        TAG = MCP7940.CLS_NAME+".write_to_SRAM():    "
        le = len(dt)
        if my_debug:
            print("\n"+TAG+f"param dt: {dt}")
            print(TAG+f"length received param dt, le: {le}")
        reg_buf = bytearray()
        reg_buf.append(MCP7940.SRAM_START_ADDRESS)
        if my_debug:
            print(TAG+f"reg_buf: {reg_buf}, hex(list(reg_buf)[0]): {hex(list(reg_buf)[0])}")
        if le >= 64:
            dt2 = dt[:64]  # only the bytes 0-6. Cut 7 and 8 because 7 is too large and 8 could be negative]
        else:
            dt2 = dt
        le2 = len(dt2)
        if my_debug:
            print(TAG+f"le2: {le2}")
  
        if my_debug:
            print("\n"+TAG+f"dt2: {dt2}")
            print(TAG+f"MCP7940.write_to_SRAM(): Writing this datetime tuple (dt2): \'{dt2}\' to user memory (SRAM)")
        
        if le2 == 7:
            year, month, date, hours, minutes, seconds, weekday  = dt2
            if year >= 2000:
                year -= 2000
            dt4 = [seconds, minutes, hours, weekday, date, month, year]
        elif le2 == 9:
            year, month, date, hours, minutes, seconds, weekday, is_12hr, is_PM = dt2
            if year >= 2000:
                year -= 2000
            dt4 = [seconds, minutes, hours, weekday, date, month, year, is_12hr, is_PM]
        
        ampm = "" 
                
        le4 = len(dt4)
        nr_bytes = le4
        
        if my_debug:
            if le4 == 7:
                print(TAG+f"nr_bytes: {nr_bytes+1}, sec: {seconds}, min: {minutes}, hr: {hours}, wkday: {weekday}, dt: {date}, mon: {month}, yy: {year}")
            elif le4 == 9:
                print(TAG+f"nr_bytes: {nr_bytes+1}, sec: {seconds}, min: {minutes}, hr: {hours}, wkday: {weekday}, dt: {date}, mon: {month}, yy: {year},  is_12hr: {is_12hr}, is_PM: {is_PM}")
                print()
        # Reorder
        # Write in reversed order (as in the registers 0x00-0x06 of the MP7940)

        if my_debug:
            print(TAG+f"dt4: {dt4}, nr_bytes: {nr_bytes}")
        out_buf = bytearray() # 
        #out_buf.append(MCP7940.SRAM_START_ADDRESS)
        out_buf.append(nr_bytes+1) # add the number of bytes + the nr_bytes byte itself
        ads = MCP7940.SRAM_START_ADDRESS
        
        for _ in range(le4):  # don't save tm_yday (can be > 255) and don't save tm_isdst (can be negative)
            out_buf.append(dt4[_])

        le = len(out_buf)
        if my_debug:
            print(TAG+f"out_buf: {out_buf}, type: {type(out_buf)}, number of bytes to be written: {nr_bytes}")
            print(TAG+f"writing to SRAM: list(out_buf): {list(out_buf)}")
        try:
            self._i2c.writeto_mem(MCP7940.ADDRESS, ads, out_buf)  # Write the data to SRAM
        except OSError as e:
            print(TAG+f"Error: {e}")
            return -1
        return nr_bytes  # return nr_bytes to show command was successful

 # Read datetime stamp from SRAM
    """ Function added by @Paulskpt """
    def read_fm_SRAM(self):
        TAG = MCP7940.CLS_NAME+".read_fm_SRAM():     "
        num_registers = 0x40
        dt = bytearray(num_registers) #  read all the SRAM memory. was: (num_regs)
        ads = MCP7940.SRAM_START_ADDRESS
        
        if my_debug:
            print(TAG+f"\nbefore reading from SRAM, dt: {dt} = list(dt): {list(dt)}")
        try:
            dt = self._i2c.readfrom_mem(MCP7940.ADDRESS, ads, num_registers)
        except OSError as e:
            print(TAG+f"Error: {e}")
            return (0,)

        if not dt:
            return (0,)  # Indicate received 0 bytes
        if len(dt) == 0:
            return (0,) # Indicate received 0 bytes

        nr_bytes = dt[0] # extract the number of bytes saved
        dt = list(dt[:nr_bytes])
        if my_debug:
            print(TAG+f"received from RTC SRAM: nr_bytes: {nr_bytes}, ", end='\n')
            print(TAG+f"dt: {dt}")
        
        if nr_bytes == 8:
            nr_bytes2, seconds, minutes, hours, weekday, date, month, year = dt
            # reorder:
            dt2 = (nr_bytes2, year, month, date, weekday, hours, minutes, seconds)
        elif nr_bytes == 10:
            nr_bytes2, seconds, minutes, hours, weekday, date, month, year, is_12hr, is_PM = dt
            # reorder:
            dt2 = (nr_bytes2, year, month, date, weekday, hours, minutes, seconds, is_12hr, is_PM)
        else:
            dt2 = dt
        if my_debug:
            print(TAG+"return value dt2: {}, type(dt2): {} ".format(dt2, type(dt2)))
            print()
        return dt2
    
    def pr_regs(self):
        # display the device values for the bits
        print(f"pr_regs(): {list(self.dt_sram)}")



    # This class is not used?
    class DATA:
        
        def __init__(self, i2c, address):
            self._i2c = i2c
            self._address = address
            self._memory_start = 0x20
            #self._memory_start = const(0x20)

        def __getitem__(self, key):
            get_byte = lambda x: self._i2c.readfrom_mem(self._address, x + self._memory_start, 1)(x)
            if type(key) is int:
                if my_debug:
                    print('key: {}'.format(key))
                return get_byte(key)
            elif type(key) is slice:
                if my_debug:
                    print('start: {} stop: {} step: {}'.format(key.start, key.stop, key.step))
                    # fixme: Could be more efficient if we check for a contiguous block
                    # Loop over range(64)[slice]
                    return [get_byte(i) for i in range(64)[key]]

            def __setitem__(self, key, value):
                if type(key) is int:
                    if my_debug:
                        print('key: {}'.format(key))
                elif type(key) is slice:
                    if my_debug:
                        print('start: {} stop: {} step: {}'.format(key.start, key.stop, key.step))
                if my_debug:
                    print(value)
