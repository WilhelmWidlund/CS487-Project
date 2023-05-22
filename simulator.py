from dataclasses import dataclass
from threading import Thread
from random import random, getrandbits
import time

import mixbox

# constants
TANK_VOLUME = 100  # liters
TANK_OUTFLOW = 2  # liter / s
BASIN_VOLUME = 500  # liters
BASIN_OUTFLOW = 5  # liter / s

# Level constants
TANK_VERY_LOW = 0.1*TANK_VOLUME
TANK_LOW = 0.2*TANK_VOLUME
TANK_HIGH = 0.8*TANK_VOLUME
TANK_VERY_HIGH = 0.9*TANK_VOLUME
DEFAULT_LEVELS = [TANK_VERY_LOW, TANK_LOW, TANK_HIGH, TANK_VERY_HIGH]

# Default breakdown probabilities per timestep
DEFAULT_BREAK_PROBS = {"level_sensor": 0.0001,
                       "vl_sensor": 0.0001,
                       "l_sensor": 0.0001,
                       "h_sensor": 0.0001,
                       "vh_sensor": 0.0001,
                       "outflow_sensor": 0.0001,
                       "color_sensor": 0.0001,
                       "valve_actuator": 0.0001,
                       "fill_actuator": 0.0001,
                       "flush_actuator": 0.0001}

# Alarm definitions: Key = priority level, value = descriptive string
DEFAULT_ALARM_DEFS = {1: "The tank is leaking",
                      2: "Uncontrolled inflow to tank",
                      3: "Level stagnation",
                      4: "Level conflict: very high",
                      5: "Level conflict: high",
                      6: "Level conflict: low",
                      7: "Level conflict: very low",
                      8: "The tank is empty",
                      9: "The tank level is very low",
                      10: "The tank level is low",
                      11: "The tank level is very high",
                      12: "The tank is currently emptying"}

@dataclass
class PaintMixture:
    """
    Represents a paint mixture consisting of several basic colors
    """
    cyan: int = 0
    magenta: int = 0
    yellow: int = 0
    black: int = 0
    white: int = 0

    @property
    def volume(self):
        """
        get the volume of the paint mixture
        """
        return self.cyan + self.magenta + self.yellow + self.black + self.white

    def __add__(self, b):
        """
        add the volume of two paint mixtures
        :param b: other instance
        :return: PaintMixture instance that represents the sum of self + b
        """
        return PaintMixture(self.cyan + b.cyan, self.magenta + b.magenta, self.yellow + b.yellow, self.black + b.black,
                            self.white + b.white)

    def __sub__(self, b):
        """
        subtract another volume from this paint mixture
        :param b: other instance
        :return: PaintMixture instance that represents the self - b
        """
        return PaintMixture(self.cyan - b.cyan, self.magenta - b.magenta, self.yellow - b.yellow, self.black - b.black,
                            self.white - b.white)

    def __mul__(self, b):
        """
        multiply the volume of this paint mixture by a factor
        :param b: multiplication factor
        :return: PaintMixture instance that represents self*b
        """
        return PaintMixture(self.cyan * b, self.magenta * b, self.yellow * b, self.black * b,
                            self.white * b)


def CMYKToRGB(c, m, y, k):
    """
    convert from CMYK to RGB colors
    """
    r = (255 * (1 - c) * (1 - k))
    g = (255 * (1 - m) * (1 - k))
    b = (255 * (1 - y) * (1 - k))
    return r, g, b


# RGB colors
CYAN_RGB = CMYKToRGB(1, 0, 0, 0)
MAGENTA_RGB = CMYKToRGB(0, 1, 0, 0)
YELLOW_RGB = CMYKToRGB(0, 0, 1, 0)
BLACK_RGB = (0, 0, 0)
WHITE_RGB = (255, 255, 255)

# mixbox colors
CYAN = mixbox.rgb_to_latent(CYAN_RGB)
MAGENTA = mixbox.rgb_to_latent(MAGENTA_RGB)
YELLOW = mixbox.rgb_to_latent(YELLOW_RGB)
BLACK = mixbox.rgb_to_latent(BLACK_RGB)
WHITE = mixbox.rgb_to_latent(WHITE_RGB)


class PaintTank:
    """
    Class represents a paint tank
    """
    def __init__(self, name, volume, outflow_rate, paint: PaintMixture, level_refs=None, break_probs=None, connected_to=None, alarm_defs=None):
        """
        Initializes the paint tank with the give parameters
        :param name: given human-friendly name of the tank, e.g. "cyan"
        :param volume: total volume of the tank
        :param outflow_rate: maximum outgoing flow rate when the valve is fully open
        :param paint: initial paint mixture in the tank
        :param connected_to: whether the tank outflow is connected to another object
        """
        self.name = name
        if name == "mixer":
            self.connected_from = []
        self.tank_volume = volume
        self.outflow_rate = outflow_rate
        self.initial_paint = paint
        self.connected_to = connected_to
        self.paint = self.initial_paint
        self.valve_ratio = 0  # valve closed
        self.outflow = 0
        # Storage vectors, each element is (time_x, value_at_time_x). Index -1 holds the most recent value
        # Format for time_x is = (month, day, hour, minute, second)
        # Initialized with time_x = False to signify that this storage space is not yet used.
        self.level_history = [(False, 0)] * 120
        self.valve_history = [(False, 0)] * 120
        # Initially, set latest level same as initial level for the first timestep alarm check not to crash
        self.level_history[-1] = (time.localtime()[1:6], self.paint.volume / self.tank_volume)
        if level_refs is None:
            self.very_low_ref = DEFAULT_LEVELS[0]
            self.low_ref = DEFAULT_LEVELS[1]
            self.high_ref = DEFAULT_LEVELS[2]
            self.very_high_ref = DEFAULT_LEVELS[3]
        if break_probs is None:
            self.break_probabilities = DEFAULT_BREAK_PROBS
        if alarm_defs is None:
            self.alarm_definitions = DEFAULT_ALARM_DEFS  # Default dictionary of possible alarms
        self.alarms = {}    # Dictionary of alarms that should be displayed, default empty (no alarms)
        # key = Priority level, lower = worse
        # value = Time of alarm, format (month, day, hour, minute, second)
        # Possible default alarms can be seen in DEFAULT_ALARM_DEFS, at line 34
        self.errors = []    # List of errors that have occurred to the tank, default empty
        # These represent malfunctions, and can't be directly discovered.
        # The idea is that the simulation knows these, for the purposes of simulating a broken component properly.
        # The user/GUI does NOT know about these, rather it is up to sensors to detect these.
        # Possible errors:
        # "level_sensor": continuous level sensor is broken
        # "vl_sensor": binary very low level sensor is broken
        # "l_sensor": binary low level sensor is broken
        # "h_sensor": binary high level sensor is broken
        # "vh_sensor": binary very high level sensor is broken
        # "outflow_sensor": outflow sensor is broken
        # "color_sensor": color sensor is broken
        # "valve_actuator": valve actuator is broken, valve is stuck and can't be read
        # "fill_actuator": tank filling actuator is broken, can't fill tank
        # "flush_actuator": tank flushing actuator is broken, can't flush tank

    def add(self, inflow):
        """
        Add paint to the tank
        :param inflow: paint to add
        """
        self.paint += inflow

    def fill(self, level=1.0):
        """
        fill up the tank based on the specified initial paint mixture
        """
        # Check for fill error
        if "fill_actuator" not in self.errors:
            # Fill tank using default input level=1.0
            self.paint = self.initial_paint * (level * self.tank_volume / self.initial_paint.volume)
        # Else, filling actuator is broken so don't fill...

    def flush(self):
        """
        flush the tank
        """
        # Check for flush error
        if "flush_actuator" not in self.errors:
            # Flush tank
            self.paint = PaintMixture()
        # Else, flushing actuator is broken so don't flush...

    def get_level(self):
        """
        get the current level of the tank measured from the bottom
        range: 0.0 (empty) - 1.0 (full)
        """
        # Check for level sensor error
        if "level_sensor" not in self.errors:
            # Level sensor works fine
            return self.paint.volume / self.tank_volume
        else:
            # Level sensor broken: give random value in valid range
            return random()

    def get_valve(self):
        """
        get the current valve setting:
        range: 0.0 (fully closed) - 1.0 (fully opened)
        """
        # Check for valve error
        if "valve_actuator" not in self.errors:
            # The valve works fine
            return self.valve_ratio
        else:
            # The valve, including its sensor, is broken. Give random value in valid range
            return random()

    def set_valve(self, ratio):
        """
        set the valve, enforces values between 0 and 1
        """
        # Check for valve error
        if "valve_actuator" not in self.errors:
            # The valve works fine
            self.valve_ratio = min(1, max(0, ratio))
        # Else, the valve is stuck so do nothing...
        else:
            pass

    def get_outflow(self):
        """
        get volume of the paint mixture flowing out of the tank
        """
        # Check for outflow sensor error
        if "outflow_sensor" not in self.errors:
            # Outflow sensor works fine
            return self.outflow
        else:
            # Outflow sensor broken: give random value in valid range
            return self.outflow_rate * random()

    def get_color_rgb(self):
        """
        get the color of the paint mixture in hex format #rrggbb
        """
        volume = self.paint.volume
        if volume == 0:
            return "#000000"
        # https://github.com/scrtwpns/mixbox/blob/master/python/mixbox.py
        z_mix = [0] * mixbox.LATENT_SIZE
        if "color_sensor" not in self.errors:
            # The color sensor works fine
            for i in range(len(z_mix)):
                z_mix[i] = (self.paint.cyan / volume * CYAN[i] +
                            self.paint.magenta / volume * MAGENTA[i] +
                            self.paint.yellow / volume * YELLOW[i] +
                            self.paint.black / volume * BLACK[i] +
                            self.paint.white / volume * WHITE[i]
                            )
        else:
            # Color sensor broken: return random color
            for i in range(len(z_mix)):
                z_mix[i] = (self.tank_volume*random() / volume * CYAN[i] +
                            self.tank_volume*random() / volume * MAGENTA[i] +
                            self.tank_volume*random() / volume * YELLOW[i] +
                            self.tank_volume*random() / volume * BLACK[i] +
                            self.tank_volume*random() / volume * WHITE[i]
                            )
        rgb = mixbox.latent_to_rgb(z_mix)
        return "#%02x%02x%02x" % (rgb[0], rgb[1], rgb[2])

    def get_vl_readout(self):
        """
        Read the binary "very low" sensor
        """
        # Check for "very low" sensor error
        if "vl_sensor" not in self.errors:
            # The "very low" sensor works fine
            if self.get_level() > self.very_low_ref:
                return False
            else:
                return True
        else:
            return bool(getrandbits(1))

    def get_l_readout(self):
        """
        Read the binary "low" sensor
        """
        # Check for "low" sensor error
        if "l_sensor" not in self.errors:
            # The "low" sensor works fine
            if self.get_level() > self.low_ref:
                return False
            else:
                return True
        else:
            return bool(getrandbits(1))

    def get_h_readout(self):
        """
        Read the binary "high" sensor
        """
        # Check for "high" sensor error
        if "h_sensor" not in self.errors:
            # The "high" sensor works fine
            if self.get_level() > self.high_ref:
                return True
            else:
                return False
        else:
            return bool(getrandbits(1))

    def get_vh_readout(self):
        """
        Read the binary "very high" sensor
        """
        # Check for "very high" sensor error
        if "h_sensor" not in self.errors:
            # The "very high" sensor works fine
            if self.get_level() > self.very_high_ref:
                return True
            else:
                return False
        else:
            return bool(getrandbits(1))

    def get_alarms(self):
        """
        Read the alarms dictionary
        """
        text_alarm = ""
        for keys in self.alarms:
            text_alarm = text_alarm+ "{}:{}:{}:{}:{}/".format(self.alarms[keys][0],self.alarms[keys][1],self.alarms[keys][2],self.alarms[keys][3],self.alarms[keys][4])+self.name+"/"+self.DEFAULT_ALARM_DEFS[keys]+"|"
        return text_alarm

    def read_level_sensors(self):
        """
        Read all the level-related sensors
        """
        return [self.get_level(), self.get_vl_readout(), self.get_l_readout(),
                self.get_h_readout(), self.get_vh_readout()]

    def update_level_ref_alarms(self, level_readouts):
        """
        Update any alarms related to the current tank level in relation to the reference levels.
        Expects self.alarm_definitions = DEFAULT_ALARM_DEFS
        """
        # Check for very high level alarm
        # Only the mixer tank can have it
        if level_readouts[4] and self.name == "mixer":
            if 11 not in self.alarms:
                self.alarms[11] = time.localtime()[1:6]
            # If the level is very high, it can't be below any of the other thresholds
            return
        elif 11 in self.alarms and self.name == "mixer":
            # Clear previous very high level alarm
            del self.alarms[11]
        # Check for Empty, very low and low level alarms
        # Begins from empty and works upward, as an alarm for a lower level precludes any alarms for higher levels
        # Check for Empty alarms
        if level_readouts[0] == 0:
            if 8 not in self.alarms:
                self.alarms[8] = time.localtime()[1:6]
            return
        elif 8 in self.alarms:
            # Clear previous empty alarm
            del self.alarms[8]
        # Check for very low level alarms
        # Only color tanks can have it
        if level_readouts[1] and not self.name == "mixer":
            if 9 not in self.alarms:
                self.alarms[9] = time.localtime()[1:6]
            return
        elif 9 in self.alarms and not self.name == "mixer":
            # Clear previous very low level alarm
            del self.alarms[9]
        # Check for low level alarms
        # Only color tanks can have it
        if level_readouts[2] and not self.name == "mixer":
            if 10 not in self.alarms:
                self.alarms[10] = time.localtime()[1:6]
            return
        elif 10 in self.alarms and not self.name == "mixer":
            # Clear previous low level alarm
            del self.alarms[10]

    def update_level_conflict_alarms(self, level_readouts, current_valve):
        """
        Update any alarms that suggest conflicts between sensor readings in relation to the tank level.
        Expects level_readouts = [self.get_level(), self.get_vl_readout(), self.get_l_readout(),
                                  self.get_h_readout(), self.get_vh_readout()]
        Expects self.alarm_definitions = DEFAULT_ALARM_DEFS
        """
        # Stagnation alarm: Valve is open but level does not go down
        if current_valve > 0 and level_readouts[0] >= self.level_history[0][1]:
            if 3 not in self.alarms:
                self.alarms[3] = time.localtime()[1:6]
        elif 3 in self.alarms:
            # Clear previous stagnation alarm if fixed
            del self.alarms[3]
        # Uncontrolled input of mixer tank: direct effect of leak alarm in connected tank
        if self.name == "mixer":
            for tank_obj in self.connected_from:
                if 1 in tank_obj.alarms and 2 not in self.alarms:
                    self.alarms[2] = time.localtime()[1:6]
                elif 2 in self.alarms:
                    # Clear previous uncontrolled inflow alarm if fixed
                    del self.alarms[2]
        # Check for own level conflicts
        if level_readouts[0] > self.very_high_ref and not level_readouts[4]:
            # Level conflict: very high level alarm
            if 4 not in self.alarms:
                self.alarms[4] = time.localtime()[1:6]
        elif 4 in self.alarms:
            # Clear previous Level conflict alarm
            del self.alarms[4]
        elif level_readouts[0] > self.high_ref and not level_readouts[3]:
            # Level conflict: high level alarm
            if 5 not in self.alarms:
                self.alarms[5] = time.localtime()[1:6]
        elif 5 in self.alarms:
            # Clear previous Level conflict alarm
            del self.alarms[5]
        elif level_readouts[0] < self.low_ref and not level_readouts[2]:
            # Level conflict: low level alarm
            if 6 not in self.alarms:
                self.alarms[6] = time.localtime()[1:6]
        elif 6 in self.alarms:
            # Clear previous Level conflict alarm
            del self.alarms[6]
        elif level_readouts[0] < self.very_low_ref and not level_readouts[1]:
            # Level conflict: very low level alarm
            if 7 not in self.alarms:
                self.alarms[7] = time.localtime()[1:6]
        elif 7 in self.alarms:
            # Clear previous Level conflict alarm
            del self.alarms[7]

    def update_alarms(self):
        """
        Read sensors and use readings to update the current alarms.

        * Add them to self.alarms if the condition exists, and they are not yet added
        * Do nothing if the condition exists and the alarm has already been added
        * Clear them if they are in self.alarms and the condition no longer exists

        Expects self.alarm_definitions = DEFAULT_ALARM_DEFS
        """
        # [self.get_level(), self.get_vl_readout(), self.get_l_readout(), self.get_h_readout(), self.get_vh_readout()]
        level_readouts = self.read_level_sensors()
        current_valve = self.get_valve()
        # Alarms that suggest something is broken
        # 1. Leak alarm
        if level_readouts[0] < self.level_history[0][1] and current_valve == 0:
            if 1 not in self.alarms:
                self.alarms[1] = time.localtime()[1:6]
        elif 1 in self.alarms:
            # Clear possible previous alarm if the leak has stopped
            del self.alarms[1]
        # 2. Conflicting sensor value alarms
        self.update_level_conflict_alarms(level_readouts, current_valve)
        # 3. Reference level alarms
        self.update_level_ref_alarms(level_readouts)
        # 4. Emptying alarm
        if current_valve > 0 and level_readouts[0] > 0:
            if 12 not in self.alarms:
                self.alarms[12] = time.localtime()[1:6]
        elif 12 in self.alarms:
            # Clear possible previous alarm if the tank is no longer emptying
            del self.alarms[12]

    def update_storage(self):
        """
        Update the data storage variables for the current cycle:
        Shift the lists, discarding the oldest entries and inserting the current time and values
        """
        self.level_history.pop(0)
        self.level_history.append((time.localtime()[1:6], self.get_level()))
        self.valve_history.pop(0)
        self.valve_history.append((time.localtime()[1:6], self.get_valve()))

    def simulate_timestep(self, interval):
        """
        update the simulation based on the specified time interval
        """
        # Randomly risk that something or other breaks down in this timestep
        for key in self.break_probabilities:
            # Check if the device breaks
            if key not in self.errors and self.break_probabilities[key] > random():
                # Add broken device to list of broken devices
                self.errors.append(str(key))

        # calculate the volume of the paint flowing out in the current time interval
        outgoing_volume = self.valve_ratio * self.outflow_rate * interval
        if outgoing_volume >= self.paint.volume:
            # tank will be empty within the current time interval
            out = self.paint
            self.paint = PaintMixture()  # empty
        else:
            # tank will not be empty
            out = self.paint * (outgoing_volume / self.paint.volume)
            self.paint -= out

        # set outgoing paint volume
        self.outflow = out.volume

        if self.connected_to is not None:
            # add outgoing paint into the connected tank
            self.connected_to.add(out)

        # check if tank has overflown
        if self.paint.volume > self.tank_volume:
            # keep it at the maximum fill level
            self.paint *= self.tank_volume / self.paint.volume

        # Update the alarms currently being discovered and displayed
        self.update_alarms()

        # Store current level and valve values
        self.update_storage()

        # return outgoing paint mixture
        return out


class Simulator(Thread):
    """
    simulation of a paint mixing plant
    """

    def __init__(self):
        Thread.__init__(self)
        self.stopRequested = False
        self.sim_time = 0

        # set up the mixing tank, initially empty
        self.mixer = PaintTank("mixer", BASIN_VOLUME, BASIN_OUTFLOW, PaintMixture())

        # set up the paint storage tanks and connect them to the mixing tank
        self.tanks = [
            PaintTank("cyan", TANK_VOLUME, TANK_OUTFLOW, PaintMixture(TANK_VOLUME, 0, 0, 0, 0),
                      connected_to=self.mixer),  # cyan
            PaintTank("magenta", TANK_VOLUME, TANK_OUTFLOW, PaintMixture(0, TANK_VOLUME, 0, 0, 0),
                      connected_to=self.mixer),  # magenta
            PaintTank("yellow", TANK_VOLUME, TANK_OUTFLOW, PaintMixture(0, 0, TANK_VOLUME, 0, 0),
                      connected_to=self.mixer),  # yellow
            PaintTank("black", TANK_VOLUME, TANK_OUTFLOW, PaintMixture(0, 0, 0, TANK_VOLUME, 0),
                      connected_to=self.mixer),  # black
            PaintTank("white", TANK_VOLUME, TANK_OUTFLOW, PaintMixture(0, 0, 0, 0, TANK_VOLUME),
                      connected_to=self.mixer),  # white
            self.mixer  # mixing basin
        ]
        # Connect mixer back to the paint storage tanks (for uncontrolled inflow alarm check)
        for tank_obj in self.tanks:
            if tank_obj.name != "mixer":
                self.mixer.connected_from.append(tank_obj)

    def get_paint_tank_by_name(self, name):
        """
        Helper method to get a reference to the PaintTank instance with the given name.
        Returns None if not found.
        """
        return next((tank for tank in self.tanks if tank.name == name), None)

    def simulate(self, interval: float):
        """
        advance simulation for a simulated duration of the specified time interval
        """
        for tank in self.tanks:
            tank.simulate_timestep(interval)

        # increase simulation time
        self.sim_time += interval

    def stop(self):
        """
        Request the simulation thread to stop.
        """
        self.stopRequested = True

    def run(self) -> None:
        """
        main function for the simulation thread
        """
        interval = 1.0  # 1 second
        while not self.stopRequested:
            self.simulate(interval=interval)
            time.sleep(interval)


if __name__ == "__main__":

    # create the simulator
    simulator = Simulator()

    # set initial conditions, open valve of first tank by 50%
    simulator.tanks[0].set_valve(50)

    # run the simulation for the specified time step and print some information
    for i in range(10):
        simulator.simulate(1.0)
        print("============================================")
        for tank in simulator.tanks:
            print("Name: %s Volume: %.2f/%.2f" % (tank.name, tank.paint.volume, tank.tank_volume),
                  "paint: %s" % tank.paint)