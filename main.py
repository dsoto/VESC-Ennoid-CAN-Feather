# can feather dashboard for vesc ennoid

import struct
import time
import canio
import board
import busio
import sdcardio
import storage
import adafruit_sdcard
import os
import digitalio
import displayio
from adafruit_progressbar import ProgressBar
import terminalio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import label
from adafruit_hx8357 import HX8357

spi = board.SPI()

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

strings = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']

class DERIVED:
    def __init__(self):
        self.last_sample = time.monotonic()
        self.sampling_interval = 0.5
        self.string_formats = [('high_cell_voltage',     vehicle_data, 'Vh', 3),
                        ('low_cell_voltage',     vehicle_data, 'Vl', 3)]

    def update(self, ready, strings):
        if ready == True:
            print('o', end='')
            # reset time stamps
            time_delta = time.monotonic() - self.last_sample
            self.last_sample = time.monotonic()
            derived_data['speed'] = vehicle_data['motor_rpm'] * vehicle_parameters['wheel_circumference'] / 23 / 60.0
            derived_data['distance'] += derived_data['speed'] * time_delta / 1000.0
            derived_data['energy'] += vehicle_data['battery_current'] * vehicle_data['battery_voltage'] * time_delta / 3600.0
            derived_data['charge'] += vehicle_data['battery_current'] * time_delta / 3600.0
            self.make_strings(strings)
        return False

    def make_strings(self, strings):

        for i, l in enumerate(self.string_formats):
            if l[1][l[0]] == None:
                strings[i] = f'{l[2]} ---'
            else:
                strings[i] = f'{l[2]} {l[1][l[0]]:.2f}'

class CONSOLE:

    def __init__(self):
        self.display_update_seconds = 0.05
        self.last_display = time.monotonic()
        # (key, data dictionary, display abbreviation, precision)
        self.display = [
                        ('speed',     derived_data, 'S',   1),
                        ('motor_rpm', vehicle_data, 'rpm', 0),
                        ('high_cell_voltage',     vehicle_data, 'Vh', 3),
                        ('low_cell_voltage',     vehicle_data, 'Vl', 3),
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
        self.num_display = len(self.display)
        self.line_counter = 0

    def update(self):
        if time.monotonic() - self.last_display > self.display_update_seconds:
            # self.print_to_console()
            self.print_to_console_by_line()
            self.last_display = time.monotonic()

    def print_to_console(self):
        print()
        for l in self.display:
            # TODO: how to format number of decimal places
            #print(f'{l[2]} {l[1][l[0]]:.{l[3]}f}', end=' | ')
            if l[1][l[0]] == None:
                print(f'{l[2]} ---', end=' | ')
            else:
                print(f'{l[2]} {l[1][l[0]]:.2f}', end=' | ')
        print(f'{time.monotonic():.3f}')

    def print_to_console_by_line(self):
        print()
        l = self.display[self.line_counter]
        if self.line_counter >= (self.num_display - 1):
            self.line_counter = 0
        else:
            self.line_counter += 1
        if l[1][l[0]] == None:
            print(f'{l[2]} ---', end=' | ')
        else:
            print(f'{l[2]} {l[1][l[0]]:.2f}', end=' | ')

class CANBUS:

    def __init__(self):

        self.can_timeout = 2.0
        self.last_read = time.monotonic()
        if hasattr(board, 'BOOST_ENABLE'):
            boost_enable = digitalio.DigitalInOut(board.BOOST_ENABLE)
            boost_enable.switch_to_output(True)

        self.can = canio.CAN(rx=board.CAN_RX, tx=board.CAN_TX, baudrate=500_000, auto_restart=True)
        self.listener = self.can.listen(timeout=.005)

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
                                 0x210a: [('high_battery_temp', '>i', 0, 4, 1E1),
                                          ('high_BMS_temp',     '>i', 4, 4, 1E1)]}

        self.received_flags = {k:False for k in self.packet_variables.keys()}


    def update(self, vehicle_data):
        # message = self.bus.recv(timeout=0.050)
        message = self.listener.receive()
        if message is not None:
            # print('+', end='')
            # iterate over variables and store for expected messages
            if message.id in self.packet_variables.keys():
            # if message.id in self.packet_variables.keys():
                self.received_flags[message.id] = True
                # print(self.received_flags)
                print('+', end='')
                # print(hex(message.id))
                for pv in self.packet_variables[message.id]:
                    vehicle_data[pv[0]] = struct.unpack(pv[1], message.data[pv[2]:pv[2]+pv[3]])[0]/pv[4]
            else:
                print('-', end='')
                # print(hex(message.id))
        else:
            print('.', end='')

        if time.monotonic() - self.last_read > self.can_timeout:
            for k in vehicle_data.keys():
                vehicle_data[k] = None
            self.received_flags = {k:False for k in self.packet_variables.keys()}
            self.last_read = time.monotonic()
            return False

        if all(self.received_flags.values()) == True:
            self.received_flags = {k:False for k in self.packet_variables.keys()}
            self.last_read = time.monotonic()
            return True
        else:
            return False

class SDCARD:
    def __init__(self):

        self.cs = board.D5
        self.sdcard = sdcardio.SDCard(spi, self.cs)

        self.vfs = storage.VfsFat(self.sdcard)
        self.num_data_points = 10
        self.data_point = 0
        self.start_time = 0

        # TODO: graceful fail if no SD card
        storage.mount(self.vfs, '/sd')

        self.state = 'write'
        self.last_write_time = 0.0
        self.write_interval = 1.00
        self.start_time = 0.0

        files = os.listdir('/sd/')

        i = 0
        while True:
            filename = 'test_{:02d}.csv'.format(i)
            print(filename)
            i = i + 1
            if filename not in files:
                self.filename = '/sd/' + filename
                break

        with open(self.filename, 'w') as file:
            file.write('time,hv,lv,battery_voltage,battery_current,battery_voltage_BMS,battery_current_BMS,motor_current,battery_temperature,BMS_temperature,motor_temperature,controller_temperature,internal_resistance,distance,motor_rpm\n')

    def update(self):

        if self.state == 'idle':
            # wait until tick
            if time.monotonic() - self.last_write_time > self.write_interval:
                self.state = 'write'

        elif self.state == 'write':
            self.last_write_time = time.monotonic()
            with open(self.filename, 'a') as file:
                file.write('%0.3f' % (time.monotonic() - self.start_time))
                file.write(',')
                file.write('%0.2f' % vehicle_data['high_cell_voltage'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['low_cell_voltage'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['battery_voltage'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['battery_current'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['battery_voltage_BMS'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['battery_current_BMS'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['motor_current'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['high_battery_temp'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['high_BMS_temp'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['motor_temperature'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['controller_temperature'])
                file.write(',')
                file.write('%0.4f' % derived_data['internal_resistance'])
                file.write(',')
                file.write('%0.2f' % derived_data['distance'])
                file.write(',')
                file.write('%0.2f' % vehicle_data['motor_rpm'])
                file.write('\n')
            self.state = 'idle'
            # self.state = 'write'



class TFT:

    # def __init__(self, spi):
    def __init__(self):
        displayio.release_displays()
        # following https://learn.adafruit.com/adafruit-3-5-tft-featherwing/3-5-tft-featherwing
        self.tft_cs = board.D9
        self.tft_dc = board.D10
        self.display_bus = displayio.FourWire(spi,
                                              command=self.tft_dc,
                                              chip_select=self.tft_cs)
        self.display = HX8357(self.display_bus, width=480, height=320)
        # font = terminalio.FONT
        # font = bitmap_font.load_font("fonts/Arial-16.bdf")
        self.bar_group = displayio.Group(max_size=10)
        self.num_bars = 3
        x_border = 20
        y_border = 20
        width = self.display.width - 2 * x_border
        # height = (self.display.height - 2 * y_border) // num_bars
        height = 50
        x = self.display.width // 2 - width // 2
        y = y_border
        # self.bar_group.append(ProgressBar(x, y, width, height, 0.5))
        colors = [0xFF0000, 0x00FF00, 0x0000FF]
        # Append progress_bar to the splash group

        for i in range(self.num_bars):
            self.bar_group.append(ProgressBar(x,
                                    y + i * height,
                                    width,
                                    height,
                                    bar_color = colors[i % len(colors)]))
        self.display.show(self.bar_group)

    def update(self):

        display_lines = [[derived_data["speed"], 15],
                         [vehicle_data["high_cell_voltage"], 4.2],
                         [vehicle_data["low_cell_voltage"], 4.2]]

        # self.bar_group[0].progress = vehicle_data["high_cell_voltage"] / 4.2
        for i in range(self.num_bars):
            self.bar_group[i].progress = display_lines[i][0]/display_lines[i][1]
        # self.bar_group[0].progress = derived_data["speed"] / 15.0
        # self.bar_group[1].progress = vehicle_data["high_cell_voltage"] / 4.2
        self.display.show(self.bar_group)

class TFT_2:

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
        self.display.show(self.text_group)
        # self.bar_group = displayio.Group(max_size=10)
        # x_border = 20
        # y_border = 20
        # width = self.display.width - 2 * x_border
        # height = 20
        # x = self.display.width // 2 - width // 2
        # y = self.display.height - 2 * y_border
        # self.bar_group.append(ProgressBar(x, y, width, height, 0.5))
        # self.display.show(self.bar_group)

    def update(self, vehicle_data):

        # print('enter update', time.monotonic())
        # rotate through lines to get better response rate and reduce flicker

        if self.update_line == 0:
            pass
            # text = ''
            if vehicle_data["high_cell_voltage"] == None:
                text = '000.0V 000.0V'
            else:
                text = f'{vehicle_data["high_cell_voltage"]:.3f}V {vehicle_data["low_cell_voltage"]:.3f}V'
        elif self.update_line == 1:
            if vehicle_data["high_battery_temp"] == None or vehicle_data["motor_temperature"] == None:
                text = 'Tb 00 Tm 00 Tc 00 Tbms 00'
            else:
                text = f'Tb {vehicle_data["high_battery_temp"]:.0f} Tm {vehicle_data["motor_temperature"]:.0f} Tc {vehicle_data["controller_temperature"]:.0f} Tbms {vehicle_data["high_BMS_temp"]:.0f}'
        elif self.update_line == 2:
            # if abs(vehicle_data['battery_current']) < 10.0:
            if vehicle_data["motor_current"] == None or vehicle_data["battery_current_BMS"] == None or vehicle_data["battery_current"] == None:
                text = 'Im 0.0 Ic 0 Ib 0'
            else:
                text = f'Im {vehicle_data["motor_current"]:.1f} Ic {vehicle_data["battery_current"]:.0f} Ib {vehicle_data["battery_current_BMS"]:.0f} '
            # else:
                # text = f'B {vehicle_data["battery_current"]:.0f} M {vehicle_data["motor_current"]:.0f} C {vehicle_data["battery_current"]:.0f} '
        elif self.update_line == 3:
            pass
            text = ''
            #text = f'IR {derived_data["internal_resistance"]*1000:.0f}'
        elif self.update_line == 4:
            text = ''
            # text = f'{derived_data["speed"]:.1f}mps {derived_data["distance"]:.5f}km'
        elif self.update_line == 5:
            pass
            text = ''
            # text = f'{derived_data["charge"]:.5f}Ah {derived_data["energy"]:.5f}Wh {derived_data["trip_efficiency"]:.0f}'
        elif self.update_line == 6:
            text = ''
            #text = f'dt: {time_stamps["event_loop_elapsed"] * 1000:.0f}'

        self.text_group[self.update_line].text = text

        self.update_line += 1
        if self.update_line > 6:
            self.update_line = 0

        self.display.show(self.text_group)
        # self.bar_group[0].progress = vehicle_data["high_cell_voltage"] / 4.2
        # self.bar_group[0].progress = derived_data["speed"] / 15.0
        # self.display.show(self.bar_group)

class TFT_3:
    def __init__(self):
        self.update_interval = 0.1
        self.last_update = time.monotonic()
        self.update_line = 0
        self.update_string = 0

        displayio.release_displays()
        # following https://learn.adafruit.com/adafruit-3-5-tft-featherwing/3-5-tft-featherwing
        self.spi = board.SPI()
        self.tft_cs = board.D9
        self.tft_dc = board.D10
        self.display_bus = displayio.FourWire(self.spi,
                                              command=self.tft_dc,
                                              chip_select=self.tft_cs)
        self.display = HX8357(self.display_bus, width=480, height=320)
        font = bitmap_font.load_font("fonts/tnr-28.bdf")
        color = 0xFFFFFF
        y_spacing = 34
        y_offset = 16

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
        self.display.show(self.text_group)

    def update(self, strings):
        if time.monotonic() - self.last_update > self.update_interval:
            self.last_update = time.monotonic()
            # self.print_to_console()
            self.text_group[self.update_line].text = strings[self.update_string]

            self.update_line += 1
            if self.update_line > 6:
                self.update_line = 0

            self.update_string += 1
            if self.update_string > 5:
                self.update_string = 0

            self.display.show(self.text_group)


console = CONSOLE()
canbus = CANBUS()
derived = DERIVED()
# tft = TFT_2()
tft = TFT_3()
# sdcard = SDCARD()


debug_pin = digitalio.DigitalInOut(board.D11)
debug_pin.direction = digitalio.Direction.OUTPUT

print("ENNOID/VESC CAN reader")
while 1:
    ready_to_calculate = canbus.update(vehicle_data)
    ready_to_calculate = derived.update(ready_to_calculate, strings)
    console.update()
    debug_pin.value = True
    tft.update(strings)
    debug_pin.value = False
    # sdcard.update()
    #time.sleep(0.050)