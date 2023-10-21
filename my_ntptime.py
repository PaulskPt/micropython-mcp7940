# This is a modified version of the
# micropython's library file: ntptime.py.
# (https://github.com/micropython/micropython-lib/blob/master/micropython/net/ntptime/ntptime.py)
# See also discussion: https://github.com/orgs/micropython/discussions/10611
# In this file created a class named MYNTPTIME  
# Changes to this script: (c) 2023 by @PaulskPt (Github)
# license MIT
#
import utime

try:
    import usocket as socket
except:
    import socket
try:
    import ustruct as struct
except:
    import struct


my_debug = False

ntp_servers_dict = {
	0: "2.pt.pool.ntp.org",
	1: "1.europe.pool.ntp.org",
	2: "3.europe.pool.ntp.org",
	3: "0.adafruit.pool.ntp.org"}
	# 4: "ntp.pool.ntp.org"


class MYNTPTIME:
    
    def __init__(self):
        # The NTP host can be configured at runtime by doing: ntp.set_host('myhost.ntp.org')
        self.host_idx = 0
        self.host = ntp_servers_dict[self.host_idx]
        # The NTP socket timeout can be configured at runtime by doing: ntptime.timeout = 2
        self.timeout = 5
        self.cls_name = "MYNTPTIME"
        
    def ntp_time(self):
        TAG = self.cls_name+".ntp_time():     "
        NTP_QUERY = bytearray(48)
        NTP_QUERY[0] = 0x1B
        s = None
        try_cnt = 0
        stop = False
        while True:
            try:
                if not my_debug:
                    print(TAG+f"using host: \'{self.host}\'")
                addr = socket.getaddrinfo(self.host, 123)[0][-1]
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(self.timeout)
                res = s.sendto(NTP_QUERY, addr)
                msg = s.recv(48)
                if not my_debug:
                    print(TAG+f"msg rcvd from host ( showing just sliced part: list(msg[40:44]) ): {list(msg[40:44])}")
                if len(msg) == 48:
                    stop = True # Successful receive
            except OSError as e:
                try_cnt += 1
                if try_cnt >= len(ntp_servers_dict):
                    if s:
                        s.close()
                    return -1
                self.next_host()
                print(TAG+f"Error: {e}. Waiting 15 seconds. Trying again. Going to use ntp server: \'{ntp_servers_dict[self.host_idx]}\'.")
                utime.sleep(15)
            finally:
                if s:
                    s.close()
                if stop:
                    break
        val = struct.unpack("!I", msg[40:44])[0]

        EPOCH_YEAR = utime.gmtime(0)[0]
        if EPOCH_YEAR == 2000:
            # (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
            NTP_DELTA = 3155673600
        elif EPOCH_YEAR == 1970:
            # (date(1970, 1, 1) - date(1900, 1, 1)).days * 24*60*60
            NTP_DELTA = 2208988800
        else:
            raise Exception(TAG+"Unsupported epoch: {}".format(EPOCH_YEAR))

        return val - NTP_DELTA


    # There's currently no timezone support in MicroPython, and the RTC is set in UTC time.
    def settime(self):
        TAG = self.cls_name+".settime(): "
        t = self.ntp_time()
        if t >= 0:
            if my_debug:
                print(TAG+f"t: {t}, type(t): {type(t)}")
            import machine

            tm = utime.gmtime(t)
            machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
            return True
        else:
            print(TAG+"Setting builtin RTC with NPT datetime stamp failed")
            return False
        
    def get_host(self):
        return self.host
        
    def set_host(self, newhost):
        global host
        TAG = self.cls_name+".set_host(): "
        if isinstance(newhost, str):
            if len(newhost) > 0:
                n = newhost.find("ntp.org")
                if n >= 0:
                    if my_debug:
                        print(TAG+f"changing old host: \'{self.host}\', to: \'{newhost}\'")
                    self.host = newhost
                else:
                    print(TAG+f"new ntp host: \'{newhost}\' invalid")
                    
    def next_host(self):
        le = len(ntp_servers_dict)
        self.host_idx += 1
        if self.host_idx >= le:
            self.host_idx = 0



