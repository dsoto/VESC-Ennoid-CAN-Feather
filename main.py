# desktop implementation of listener for VESC/ENNOID CAN packets

import struct
import time
import canio
import board
import digitalio
import displayio
import terminalio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import label
from adafruit_hx8357 import HX8357

vehicle_data = {'battery_voltage':0,
                'battery_current':0,
                'battery_voltage_BMS':0,
                'battery_current_BMS':0,
                'high_cell_voltage':0,
                'low_cell_voltage':0,
                'high_battery_temp':0,
                'high_BMS_temp':0,
                'motor_rpm':0,
                'total_current':0,
                'motor_temperature':0,
                'motor_current':0,
                'controller_temperature':0,
                'dummy':0}

time_stamps = {'event_loop_current':0,
               'event_loop_previous':0,
               'event_loop_elapsed':0}

derived_data = {'internal_resistance':0.090,
                'speed':0,
                'distance':0,
                'battery_voltage_prev':0,
                'battery_current_prev':0,
                'charge':0,
                'energy':0,
                'trip_efficiency':0,
                'instantaneous_efficiency':0}

vehicle_parameters = {'wheel_circumference':1.89}

class DERIVED:
    def __init__(self):
        self.last_sample = time.monotonic()
        self.sampling_interval = 0.2

    def update(self):
        if time.monotonic() - self.last_sample > self.sampling_interval:
            self.last_sample = time.monotonic()
            self.compute_derived()
            print('o', end='')

    def compute_derived(self):
        derived_data['speed'] = vehicle_data['motor_rpm'] * vehicle_parameters['wheel_circumference'] / 23 / 60.0
        derived_data['distance'] += derived_data['speed']/1000.0

class CONSOLE:

    def __init__(self):
        self.display_update_seconds = 0.2
        self.last_display = time.monotonic()
        # (key, data dictionary, display abbreviation, precision)
        self.display = [
                        ('speed',     derived_data, 'S',   1),
                        ('motor_rpm', vehicle_data, 'rpm', 0),
                        ('high_cell_voltage',     vehicle_data, 'Vc', 3),
                        ('low_cell_voltage',     vehicle_data, 'Vc', 3),
                        ('battery_voltage',     vehicle_data, 'Vc', 1),
                        ('battery_voltage_BMS', vehicle_data, 'Vb', 1),
                        ('battery_current',     vehicle_data, 'Ic', 1),
                        ('battery_current_BMS', vehicle_data, 'Ib', 1),
                        ('motor_current',       vehicle_data, 'Im', 1),
                        ('controller_temperature', vehicle_data, 'Tc', 1),
                        ('motor_temperature', vehicle_data, 'Tm', 1),
                        ('high_battery_temp', vehicle_data, 'Tbat', 1),
                        ('high_BMS_temp', vehicle_data, 'Tbms', 1),
                        ('distance', derived_data, 'D', 1),
                        ]
    def update(self):
        if time.monotonic() - self.last_display > self.display_update_seconds:
            self.print_to_console()
            self.last_display = time.monotonic()


    def print_to_console(self):
        print()
        for l in self.display:
            # TODO: how to format number of decimal places
            #print(f'{l[2]} {l[1][l[0]]:.{l[3]}f}', end=' | ')
            print(f'{l[2]} {l[1][l[0]]:.3f}', end=' | ')
        print(f'{time.monotonic():.3f}')

class CANBUS:

    def __init__(self):

        if hasattr(board, 'BOOST_ENABLE'):
            boost_enable = digitalio.DigitalInOut(board.BOOST_ENABLE)
            boost_enable.switch_to_output(True)

        self.can = canio.CAN(rx=board.CAN_RX, tx=board.CAN_TX, baudrate=500_000, auto_restart=True)
        self.listener = self.can.listen(timeout=.5)

        # self.bus = can.interface.Bus(bustype='slcan',
        #                         channel='/dev/tty.usbmodem14101',
        #                         bitrate=500000)

        # define CAN messages to interpret
        self.packet_variables = {0x0901: [('motor_rpm',     '>l', 0, 4, 1E0),
                                          ('motor_current', '>H', 4, 2, 1E1)],
                                 0x1001: [('controller_temperature', '>H', 0, 2, 1E1),
                                          ('motor_temperature',      '>h', 2, 2, 1E1),
                                          ('battery_current',        '>h', 4, 2, 1E1)],
                                 0x1b01: [('battery_voltage',     '>H', 4, 2, 1E1)],
                                 0x1e0a: [('battery_voltage_BMS', '>i', 0, 4, 1E5),
                                          ('battery_current_BMS', '>i', 4, 4, 1E5)],
                                 0x1f0a: [('high_cell_voltage', '>i', 0, 4, 1E5),
                                          ('low_cell_voltage',  '>i', 4, 4, 1E5)],
                                 0x210a: [('high_battery_temp', '>H', 2, 2, 1E2),
                                          ('high_BMS_temp',     '>H', 6, 2, 1E2)]}

    def update(self):
        # message = self.bus.recv(timeout=0.050)
        message = self.listener.receive()
        if message is not None:
            print('+', end='')
            # iterate over variables and store for expected messages
            # if message.arbitration_id in self.packet_variables.keys():
            if message.id in self.packet_variables.keys():
                for pv in self.packet_variables[message.id]:
                    vehicle_data[pv[0]] = struct.unpack(pv[1], message.data[pv[2]:pv[2]+pv[3]])[0]/pv[4]
        else:
            print('.', end='')

class TFT:

    # def __init__(self, spi):
    def __init__(self):
        displayio.release_displays()
        # following https://learn.adafruit.com/adafruit-3-5-tft-featherwing/3-5-tft-featherwing
        self.spi = board.SPI()
        self.tft_cs = board.D9
        self.tft_dc = board.D10
        self.display_bus = displayio.FourWire(self.spi,
                                              command=self.tft_dc,
                                              chip_select=self.tft_cs)
        self.display = HX8357(self.display_bus, width=480, height=320)
        # font = terminalio.FONT
        # font = bitmap_font.load_font("fonts/Arial-16.bdf")
        font = bitmap_font.load_font("fonts/tnr-28.bdf")
        color = 0xFFFFFF
        y_spacing = 34
        y_offset = 16
        # init the group with all the labels here in an array
        self.text_labels = [label.Label(font, color=color, max_glyphs=20, x=10, y=y_offset),
                            label.Label(font, color=color, max_glyphs=20, x=10, y=y_offset + 1 * y_spacing),
                            label.Label(font, color=color, max_glyphs=20, x=10, y=y_offset + 2 * y_spacing),
                            label.Label(font, color=color, max_glyphs=20, x=10, y=y_offset + 3 * y_spacing),
                            label.Label(font, color=color, max_glyphs=20, x=10, y=y_offset + 4 * y_spacing),
                            label.Label(font, color=color, max_glyphs=20, x=10, y=y_offset + 5 * y_spacing),
                            label.Label(font, color=color, max_glyphs=20, x=10, y=y_offset + 6 * y_spacing)]
        self.text_group = displayio.Group(max_size=8)
        for tl in self.text_labels:
            self.text_group.append(tl)
        self.update_line = 0

    def update(self):

        # print('enter update', time.monotonic())
        # rotate through lines to get better response rate and reduce flicker

        if self.update_line == 0:
            pass
            # text = ''
            text = f'{vehicle_data["high_cell_voltage"]:.3f}V {vehicle_data["low_cell_voltage"]:.3f}V'
        elif self.update_line == 1:
            text = f'Tb {vehicle_data["high_battery_temp"]:.0f} Tm {vehicle_data["motor_temperature"]:.0f} Tc {vehicle_data["controller_temperature"]:.0f} Tbms {vehicle_data["high_BMS_temp"]:.0f}'
        elif self.update_line == 2:
            # if abs(vehicle_data['battery_current']) < 10.0:
            text = f'Im {vehicle_data["motor_current"]:.1f} Ic {vehicle_data["battery_current"]:.0f} Ib {vehicle_data["battery_current_BMS"]:.0f} '
            # else:
                # text = f'B {vehicle_data["battery_current"]:.0f} M {vehicle_data["motor_current"]:.0f} C {vehicle_data["battery_current"]:.0f} '
        elif self.update_line == 3:
            pass
            text = ''
            #text = f'IR {derived_data["internal_resistance"]*1000:.0f}'
        elif self.update_line == 4:
            text = f'{derived_data["speed"]:.1f}mps {derived_data["distance"]:.1f}km'
        elif self.update_line == 5:
            pass
            text = ''
            #text = f'{derived_data["charge"]:.1f}Ah {derived_data["energy"]:.0f}Wh {derived_data["trip_efficiency"]:.0f}'
        elif self.update_line == 6:
            text = ''
            #text = f'dt: {time_stamps["event_loop_elapsed"] * 1000:.0f}'

        self.text_group[self.update_line].text = text

        self.update_line += 1
        if self.update_line > 6:
            self.update_line = 0

        self.display.show(self.text_group)

console = CONSOLE()
canbus = CANBUS()
derived = DERIVED()
tft = TFT()

print("ENNOID/VESC CAN reader")
while 1:
    canbus.update()
    console.update()
    derived.update()
    tft.update()