import time, configparser
from PyP100 import PyP110
from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.align import Align

def main():
    devices = []
    default_email = ""
    default_password = ""

    config = configparser.ConfigParser()
    config.read('p110monitor.ini')
    if 'auth' in config.sections() and 'email' in config['auth'].keys():
        default_email = config['auth']['email']
    if 'auth' in config.sections() and 'password' in config['auth'].keys():
        default_password = config['auth']['password']
    
    for s in [x for x in config.sections() if x != 'auth']:
        name = s
        ip = config[s]["ip"]
        email = config[s]["email"] if "email" in config[s].keys() else default_email
        password = config[s]["password"] if "password" in config[s].keys() else default_password

        devices.append(P110Device(name, ip, email, password))

    interface = CliInterface(devices)
    interface.start()

class P110Device:
    def __init__(self, name, ip, email, password):
        self.name = name
        self.ip = ip
        self.email = email
        self.password = password
        self.connection = self.getConnection()
        self.data = {}
        self.history = []
        self.last_read = 0
    
    def getConnection(self):
        try:
            con = PyP110.P110(self.ip, self.email, self.password)
            con.handshake()
            con.login()
        except:
            con = None
        return con

    def update(self, force_new = False):
        if force_new or self.connection is None:
            self.connection = self.getConnection()
        
        if self.connection is None:
            self.data = {}
            return
        
        try:
            self.data = self.connection.getEnergyUsage()
            if "result" in self.data.keys():
                self.last_read = time.mktime(time.strptime(
                    self.data["result"]["local_time"],
                    "%Y-%m-%d %H:%M:%S"))
                self.history.append([self.last_read, self.data["result"]["current_power"]])
        except:
            if not force_new:
                self.data = self.update(True)
        
        if len(self.history) > 20000:
            # Trim history in case app runs for long time.
            # Will still result in always having at least 24 hours when
            # updated every 5 seconds.
            self.history = self.history[2000:]

        return self.data
    
    def validData(self):
        return self.data is not None and ("result" in self.data.keys())
    
    def currentPower(self):
        return self.data["result"]["current_power"] / 1000.0
    
    def average(self, minutes):
        if self.last_read == 0:
            return self.last_read
        
        count = 0
        value = 0
        for h in reversed(self.history):
            if self.last_read - h[0] > (minutes * 60):
                break
            count += 1
            value += h[1]

        return value / (count * 1000.0)

    def last24(self):
        return sum(self.data["result"]["past24h"]) / 1000.0
    
    def weekday(self, day):
        return sum(self.data["result"]["past7d"][day]) / 1000.0
    
    def month(self):
        return sum(self.data["result"]["past30d"]) / 1000.0
    
    def year(self):
        return sum(self.data["result"]["past1y"]) / 1000.0

class CliInterface:
    def __init__(self, devices):
        self.devices = devices
        self.console = Console()

    def generateLayout(self):
        layout = Layout()

        for d in self.devices:
            layout.add_split(Layout(name=d.name))

            row = layout[d.name]
            row.split_row(
                Layout(name="Now"),
                Layout(name="24h"),
                Layout(name="Month") 
            )

            data = ""
            if d.validData():
                data += "Currently: %s W\n" % self.n2s(d.currentPower())
                data += "1min avg:  %s W\n" % self.n2s(d.average(1))
                data += "5min avg:  %s W" % self.n2s(d.average(5))
            else:
                data = "disconnected"
            
            row["Now"].update(Align(
                Panel(data, title="%s, Now" % d.name),
                align="center",
                vertical="middle"
            ))

            data = ""
            if d.validData():
                data += "Last 24h:  %s kWh\n" % self.n2s(d.last24())
                data += "Today:     %s kWh\n" % self.n2s(d.weekday(6))
                data += "Yesterday: %s kWh" % self.n2s(d.weekday(5))
            else:
                data = "disconnected"
            
            row["24h"].update(Align(
                Panel(data, title="%s, Recent" % d.name),
                align="center",
                vertical="middle"
            ))

            data = ""
            if d.validData():
                data += "Past 30 days: %s kWh\n" % self.n2s(d.month())
                data += "Daily avg:    %s kWh\n" % self.n2s(d.month()/30.0)
                data += "Past year:    %s kWh" % self.n2s(d.year())
            else:
                data = "disconnected"
            
            row["Month"].update(Align(
                Panel(data, title="%s, Long term" % d.name),
                align="center",
                vertical="middle"
            ))

        return layout
    
    def n2s(self, n):
        if n >= 1000.0:
            return " %.0f" % n
        elif n >= 100.0:
            return "%.1f" % n
        elif n >= 10:
            return "%.2f" % n
        else:
            return "%.3f" %n

    def start(self):
        for d in self.devices:
            d.update()
        with Live(self.generateLayout(), refresh_per_second=1, screen=True) as live:
            while True:
                for d in self.devices:
                    d.update()
                live.update(self.generateLayout())
                time.sleep(5)

if __name__ == "__main__":
    main()
