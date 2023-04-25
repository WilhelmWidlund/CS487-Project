from dataclasses import dataclass
from threading import Thread
import time

import mixbox

# constants
TANK_VOLUME = 100  # liters
TANK_OUTFLOW = 2  # liter / s
BASIN_VOLUME = 500  # liters
BASIN_OUTFLOW = 5  # liter / s


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
    convert from RGB to CMYK colors
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
    def __init__(self, name, volume, outflow_rate, paint: PaintMixture, connected_to=None):
        """
        Initializes the paint tank with the give parameters
        :param name: given human-friendly name of the tank, e.g. "cyan"
        :param volume: total volume of the tank
        :param outflow_rate: maximum outgoing flow rate when the valve is fully open
        :param paint: initial paint mixture in the tank
        :param level: initial fill level
        """
        self.name = name
        self.tank_volume = volume
        self.outflow_rate = outflow_rate
        self.initial_paint = paint
        self.connected_to = connected_to
        self.paint = self.initial_paint
        self.valve_ratio = 0  # valve closed
        self.outflow = 0

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
        self.paint = self.initial_paint * (level * self.tank_volume / self.initial_paint.volume)

    def flush(self):
        """
        flush the tank
        """
        self.paint = PaintMixture()

    def get_level(self):
        """
        get the current level of the tank measured from the bottom
        range: 0.0 (empty) - 1.0 (full)
        """
        return self.paint.volume / self.tank_volume

    def get_valve(self):
        """
        get the current valve setting:
        range: 0.0 (fully closed) - 1.0 (fully opened)
        """
        return self.valve_ratio

    def set_valve(self, ratio):
        """
        set the valve, enforces values between 0 and 1
        """
        self.valve_ratio = min(1, max(0, ratio))

    def get_outflow(self):
        """
        get volume of the paint mixture flowing out of the tank
        """
        return self.outflow

    def get_color_rgb(self):
        """
        get the color of the paint mixture in hex format #rrggbb
        """
        volume = self.paint.volume
        if volume == 0:
            return "#000000"
        # https://github.com/scrtwpns/mixbox/blob/master/python/mixbox.py
        z_mix = [0] * mixbox.LATENT_SIZE

        for i in range(len(z_mix)):
            z_mix[i] = (self.paint.cyan / volume * CYAN[i] +
                        self.paint.magenta / volume * MAGENTA[i] +
                        self.paint.yellow / volume * YELLOW[i] +
                        self.paint.black / volume * BLACK[i] +
                        self.paint.white / volume * WHITE[i]
                        )
        rgb = mixbox.latent_to_rgb(z_mix)
        return "#%02x%02x%02x" % (rgb[0], rgb[1], rgb[2])

    def simulate_timestep(self, interval):
        """
        update the simulation based on the specified time interval
        """
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