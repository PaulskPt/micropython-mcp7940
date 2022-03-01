#
# Downloaded from: https://github.com/tinypico/micropython-mcp7940/blob/master/mcp7940.py
# On 2022-02-27
# In class MCCP7940, the following functions added by @Paulskpt:
# - weekday_N()
# - weekday_S()
# - yearday()
# - write_to_SRAM()
# - read_fm_SRAM()
# dictionary DOW added
# For the sake of readability: replaced index values like [0] ...[6] with [RTCSEC] ... [RTCYEAR]
#
from micropython import const

my_debug = False

class MCP7940:
    """
        Example usage:

            # Read time
            mcp = MCP7940(i2c)
            time = mcp.time # Read time from MCP7940
            is_leap_year = mcp.is_leap_year() # Is the year in the MCP7940 a leap year?

            # Set time
            ntptime.settime() # Set system time from NTP
            mcp.time = utime.localtime() # Set the MCP7940 with the system time
    """

    ADDRESS = const(0x6F)
    # MCP7940 registers
    RTCSEC = 0x00 # RTC seconds register
    RTCMIN = 0x01
    RTCHOUR = 0x02
    RTCWKDAY = 0x03  # RTC Weekday register
    RTCDATE = 0x04
    RTCMTH = 0x05
    RTCYEAR = 0x06
    ST = 7  # Status bit
    VBATEN = 3  # External battery backup supply enable bit
    
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

    def __init__(self, i2c, status=True, battery_enabled=True):
        self._i2c = i2c

    def start(self):
        self._set_bit(MCP7940.RTCSEC, MCP7940.ST, 1)

    def stop(self):
        self._set_bit(MCP7940.RTCSEC, MCP7940.ST, 0)

    def is_started(self):
        return self._read_bit(MCP7940.RTCSEC, MCP7940.ST)

    def battery_backup_enable(self, enable):
        self._set_bit(MCP7940.RTCWKDAY, MCP7940.VBATEN, enable)

    def is_battery_backup_enabled(self):
        return self._read_bit(MCP7940.RTCWKDAY, MCP7940.VBATEN)

    def _set_bit(self, register, bit, value):
        """ Set only a single bit in a register. To do so, need to read
            the current state of the register and modify just the one bit.
        """
        mask = 1 << bit
        current = self._i2c.readfrom_mem(MCP7940.ADDRESS, register, 1)
        updated = (current[0] & ~mask) | ((value << bit) & mask)
        self._i2c.writeto_mem(MCP7940.ADDRESS, register, bytes([updated]))

    def _read_bit(self, register, bit):
        register_val = self._i2c.readfrom_mem(MCP7940.ADDRESS, register, 1)
        return (register_val[0] & (1 << bit)) >> bit

    @property
    def time(self):
        return self._get_time()

    @time.setter
    def time(self, t):
        """
            >>> import time
            >>> time.localtime()
            (2019, 6, 3, 13, 12, 44, 0, 154)
            # 1:12:44pm on Monday (0) the 3 Jun 2019 (154th day of the year)
        """
        year, month, date, hours, minutes, seconds, weekday, yearday = t
        # Reorder
        time_reg = [seconds, minutes, hours, weekday + 1, date, month, year % 100]

        # Add ST (status) bit

        # Add VBATEN (battery enable) bit
        if my_debug:
            print(
                "MCP7940.time(): {}/{}/{} {}:{}:{} (day={})".format(
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
        # t = bytes([self.bcd_to_int(reg & filt) for reg, filt in zip(time_reg, reg_filter)])
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        # Note that some fields will be overwritten that are important!
        # fixme!
        if my_debug:
            print("MCP7940.time(): t = ", t)
        self._i2c.writeto_mem(MCP7940.ADDRESS, 0x00, bytes(t))
        
    @property
    def alarm1(self):
        return self._get_time(start_reg=0x0A)

    @alarm1.setter
    def alarm1(self, t):
        _, month, date, hours, minutes, seconds, weekday, _ = t  # Don't need year or yearday
        # Reorder
        time_reg = [seconds, minutes, hours, weekday + 1, date, month]
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F)  # No year field for alarms
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        self._i2c.writeto_mem(MCP7940.ADDRESS, 0x0A, bytes(t))

    @property
    def alarm2(self):
        return self._get_time(start_reg=0x11)

    @alarm2.setter
    def alarm2(self, t):
        _, month, date, hours, minutes, seconds, weekday, _ = t  # Don't need year or yearday
        # Reorder
        time_reg = [seconds, minutes, hours, weekday + 1, date, month]
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F)  # No year field for alarms
        t = [(self.int_to_bcd(reg) & filt) for reg, filt in zip(time_reg, reg_filter)]
        self._i2c.writeto_mem(MCP7940.ADDRESS, 0x11, bytes(t))

    def bcd_to_int(self, bcd):
        """ Expects a byte encoded with 2x 4bit BCD values. """
        # Alternative using conversions: int(str(hex(bcd))[2:])
        return (bcd & 0xF) + (bcd >> 4) * 10 

    def int_to_bcd(self, i):
        return (i // 10 << 4) + (i % 10)

    def is_leap_year(self, year):
        """ https://stackoverflow.com/questions/725098/leap-year-calculation """
        if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0:
            return True
        return False
    
    def weekday_N(self):
        """ Function added by @Paulskpt """
        dt = self._get_time()
        le = len(dt)
        return dt[le-1:][0]+1  # dt[le-1:] results in tuple: (0,) so we have to extract the first element.
    
    def weekday_S(self):
        """ Function added by @Paulskpt """       
        return MCP7940.DOW[self.weekday_N()]
    
    def yearday(self):
        """ Function added by @Paulskpt """
        dt = self._get_time()
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
        yearday = ndays
        return ndays

    def _get_time(self, start_reg = 0x00):
        num_registers = 7 if start_reg == 0x00 else 6
        time_reg = self._i2c.readfrom_mem(MCP7940.ADDRESS, start_reg, num_registers)  # Reading too much here for alarms
        reg_filter = (0x7F, 0x7F, 0x3F, 0x07, 0x3F, 0x3F, 0xFF)[:num_registers]
        if my_debug:
            print(time_reg)
            print(reg_filter)
        t = [self.bcd_to_int(reg & filt) for reg, filt in zip(time_reg, reg_filter)]
        # Reorder
        t2 = (t[MCP7940.RTCMTH], t[MCP7940.RTCDATE], t[MCP7940.RTCHOUR], t[MCP7940.RTCMIN], t[MCP7940.RTCSEC], t[MCP7940.RTCWKDAY] - 1)
        t = (t[MCP7940.RTCYEAR] + 2000,) + t2 + (0,) if num_registers == 7 else t2
        # now = (2019, 7, 16, 15, 29, 14, 6, 167)  # Sunday 2019/7/16 3:29:14pm (yearday=167)
        # year, month, date, hours, minutes, seconds, weekday, yearday = t
        # time_reg = [seconds, minutes, hours, weekday, date, month, year % 100]

        if my_debug:
            print(t)
        return t
    
    def write_to_SRAM(self, dt):
        """ Function added by @Paulskpt """
        le = len(dt)
        for _ in range(le):
            if _ == 0:
                dt2 = (dt[_] - 2000,)
            else:
                dt2 += (dt[_],)
        if my_debug:
            print("\nMCP7940.write_to_SRAM(): Writing this datetime tuple: \'{}\' to user memory (SRAM)".format(dt2))

        dt3 = bytes(dt2)
        start_reg = 0x20
        num_regs = len(dt3)
        if my_debug:
            print("MCP7940.write_to_SRAM(): dt3: {}, type: {}, number of bytes written: {}".format(dt3, type(dt3), len(dt3)))
        self._i2c.writeto_mem(MCP7940.ADDRESS, start_reg, dt3)
    
    def read_fm_SRAM(self):
        """ Function added by @Paulskpt """
        start_reg = 0x20
        num_regs = 0x8
        dt = self._i2c.readfrom_mem(MCP7940.ADDRESS, start_reg, num_regs) # Reading datetime stamp from User SRAM
        le = len(dt)
        if my_debug:
            print("MCP7940.read_fm_SRAM(): data read: {}, type: {}, bytes read: {}".format(dt, type(dt), le))
        
        dt2 = ()
        for _ in range(len(dt)):
            if _ == 0:
                dt2 += (dt[_]+2000,)
            else:
                  dt2 += (dt[_],)
        if my_debug:
            print("MCP7940.read_fm_SRAM(): dt2: {}, type(dt2): {} ".format(dt2, type(dt2)))
        return dt2


    class Data:
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
