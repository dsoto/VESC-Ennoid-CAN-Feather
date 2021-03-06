'''
Copyright 2021 Daniel Soto

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

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

vehicle_data = {'battery_voltage':None,
                'battery_current':None,
                'battery_voltage_BMS':None,
                'battery_current_BMS':None,
                'high_cell_voltage':None,
                'low_cell_voltage':None,
                'high_battery_temp':None,
                'high_BMS_temp':None,
                'motor_rpm':None,
                'total_current':None,
                'motor_temperature':None,
                'motor_current':None,
                'controller_temperature':None,
                'dummy':None}

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
                'instantaneous_efficiency':0,
                'time_delta':0}

vehicle_parameters = {'wheel_circumference':1.89}

strings = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
strings = [''] * 16

class DERIVED:
    def __init__(self):
        self.last_sample = time.monotonic()
        self.sampling_interval = 0.5
        self.string_index = 0
        self.string_formats = [('high_cell_voltage',     vehicle_data, 'Vh', 3),
                               ('high_battery_temp', vehicle_data, 'Tbat', 1),
                               ('controller_temperature', vehicle_data, 'Tc', 1),
                               ('battery_current_BMS', vehicle_data, 'Ib', 1),
                               ('battery_current',     vehicle_data, 'Ic', 1),
                               ('speed',     derived_data, 'S',   1),
                               ('distance', derived_data, 'km', 1),
                               ('motor_rpm', vehicle_data, 'rpm', 0),
                               ('low_cell_voltage',     vehicle_data, 'Vl', 3),
                               ('motor_temperature', vehicle_data, 'Tm', 1),
                               ('high_BMS_temp', vehicle_data, 'Tbms', 1),
                               ('motor_current',       vehicle_data, 'Im', 1),
                               ('battery_voltage_BMS', vehicle_data, 'Vb', 1),
                               ('energy', derived_data, 'Wh', 1),
                               ('charge', derived_data, 'Ah', 1),
                               ('time_delta', derived_data, 'dt', 3)]


    def update(self, ready, strings):
        if ready == True:
            # reset time stamps
            time_delta = time.monotonic() - self.last_sample
            print()
            print('o', end=' ')
            print(time_delta)
            self.last_sample = time.monotonic()
            if vehicle_data['motor_rpm'] is not None:
                derived_data['speed'] = vehicle_data['motor_rpm'] * vehicle_parameters['wheel_circumference'] / 23 / 60.0
            derived_data['distance'] += derived_data['speed'] * time_delta / 1000.0
            if vehicle_data['battery_current'] is not None and vehicle_data['battery_voltage'] is not None:
                derived_data['energy'] += vehicle_data['battery_current'] * vehicle_data['battery_voltage'] * time_delta / 3600.0
                derived_data['charge'] += vehicle_data['battery_current'] * time_delta / 3600.0
            derived_data['time_delta'] = time_delta
            self.make_strings(strings)
        return False

    def make_strings(self, strings):
        for l in self.string_formats:
            if l[1][l[0]] is None:
                strings[self.string_index] = f'{l[2]} ---'
            else:
                strings[self.string_index] = f'{l[2]} {l[1][l[0]]:.2f}'
            if self.string_index >= 15:
                self.string_index = 0
            else:
                self.string_index += 1


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
        for l in self.display:
            # TODO: how to format number of decimal places
            if l[1][l[0]] is None:
                print(f'{l[2]} ---', end=' | ')
            else:
                print(f'{l[2]} {l[1][l[0]]:.2f}', end=' | ')
        print(f'{time.monotonic():.3f}')

    def print_to_console_by_line(self):
        l = self.display[self.line_counter]
        if self.line_counter >= (self.num_display - 1):
            self.line_counter = 0
        else:
            self.line_counter += 1

class CANBUS:

    def __init__(self):

        self.can_timeout = 0.500
        self.last_read = time.monotonic()
        if hasattr(board, 'BOOST_ENABLE'):
            boost_enable = digitalio.DigitalInOut(board.BOOST_ENABLE)
            boost_enable.switch_to_output(True)

        self.can = canio.CAN(rx=board.CAN_RX, tx=board.CAN_TX, baudrate=500_000, auto_restart=True)
        self.listener = self.can.listen(timeout=.005)

        # define CAN messages to interpret
        self.packet_variables = {0x0901: [('motor_rpm',     '>l', 0, 4, 1E0),
                                          ('motor_current', '>h', 4, 2, 1E1)],
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

    def update_block(self, vehicle_data, ready_to_calculate):

        # start with all flags set to false
        for k in vehicle_data.keys():
            vehicle_data[k] = None
        self.received_flags = {k:False for k in self.packet_variables.keys()}

        # set timeout start
        self.last_read = time.monotonic()
        while True:
            print('.', end='')
        # loop untill all flags set or timeout
            if time.monotonic() - self.last_read > self.can_timeout:
                print('tko')
                break

            if all(self.received_flags.values()) == True:
                print('True')
                break

            message = self.listener.receive()
            if message is not None:
                if message.id in self.packet_variables.keys():
                    self.received_flags[message.id] = True
                    print('+', end='')
                    for pv in self.packet_variables[message.id]:
                        vehicle_data[pv[0]] = struct.unpack(pv[1], message.data[pv[2]:pv[2]+pv[3]])[0]/pv[4]
                else:
                    print('-', end='')
            else:
                    print('.', end='')

        return True

class SDCARD:
    def __init__(self):

        self.cs = board.D5

        try:
            self.sdcard = sdcardio.SDCard(spi, self.cs)
            self.vfs = storage.VfsFat(self.sdcard)
            storage.mount(self.vfs, '/sd')
        except:
            self.filename = None
            return

        self.num_data_points = 10
        self.data_point = 0
        self.start_time = 0

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
            data = [time.monotonic() - self.start_time,
                    vehicle_data['high_cell_voltage'],
                    vehicle_data['low_cell_voltage'],
                    vehicle_data['battery_voltage'],
                    vehicle_data['battery_current'],
                    vehicle_data['battery_voltage_BMS'],
                    vehicle_data['battery_current_BMS'],
                    vehicle_data['motor_current'],
                    vehicle_data['high_battery_temp'],
                    vehicle_data['high_BMS_temp'],
                    vehicle_data['motor_temperature'],
                    vehicle_data['controller_temperature'],
                    derived_data['internal_resistance'],
                    derived_data['distance'],
                    vehicle_data['motor_rpm']]

            with open(self.filename, 'a') as file:
                for d in data:
                    if d is not None:
                        file.write('%0.2f' % d)
                    file.write(',')
                file.write('\n')
            self.state = 'idle'
            # self.state = 'write'

class TFT:
    def __init__(self):
        self.update_interval = 1.0
        self.last_update = time.monotonic()
        self.update_line = 0
        self.update_string = 0

        displayio.release_displays()
        self.spi = board.SPI()
        self.tft_cs = board.D9
        self.tft_dc = board.D10
        self.display_bus = displayio.FourWire(self.spi,
                                              command=self.tft_dc,
                                              chip_select=self.tft_cs)
        self.display = HX8357(self.display_bus, width=480, height=320, auto_refresh=False)
        font = terminalio.FONT
        color = 0xFFFFFF
        y_spacing = 34
        y_offset = 16

        self.text_labels = [label.Label(font, scale=3, color=color, max_glyphs=20, x=10, y=y_offset),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=10, y=y_offset + 1 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=10, y=y_offset + 2 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=10, y=y_offset + 3 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=10, y=y_offset + 4 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=10, y=y_offset + 5 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=10, y=y_offset + 6 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=10, y=y_offset + 7 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=240, y=y_offset),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=240, y=y_offset + 1 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=240, y=y_offset + 2 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=240, y=y_offset + 3 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=240, y=y_offset + 4 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=240, y=y_offset + 5 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=240, y=y_offset + 6 * y_spacing),
                            label.Label(font, scale=3, color=color, max_glyphs=20, x=240, y=y_offset + 7 * y_spacing)]

        self.text_group = displayio.Group(max_size=16)
        for tl in self.text_labels:
            self.text_group.append(tl)
        self.display.show(self.text_group)


    def update_line_by_line(self, strings):
        # if time.monotonic() - self.last_update > self.update_interval:
            # print('t', end='')
            self.last_update = time.monotonic()
            # self.print_to_console()
            self.text_group[self.update_line].text = strings[self.update_string]

            self.update_line += 1
            if self.update_line > 15:
                self.update_line = 0

            self.update_string += 1
            if self.update_string > 15:
                self.update_string = 0

            #self.display.show(self.text_group)
            self.display.refresh(target_frames_per_second=None)

    def update_all(self, strings):
        if True:
            self.last_update = time.monotonic()
            # self.print_to_console()
            for i in range(16):
                self.text_group[i].text = strings[i]

            # self.display.refresh(target_frames_per_second=None)
            # self.display.refresh(target_frames_per_second=1)
            self.display.refresh()

class UART:
    def __init__(self):
        self.uart = busio.UART(board.TX, board.RX, baudrate=115200, timeout=0.1)

    def update(self, vehicle_data):

        # initialize data
        for k in vehicle_data.keys():
            vehicle_data[k] = None

        self.update_EBMS(vehicle_data)
        self.update_ZESC(vehicle_data)

    def update_EBMS(self, vehicle_data):
        request = bytes([0x02, 0x01, 0x04, 0x40, 0x84, 0x03])
        packet_length = 55

        EBMS_data = [['battery_voltage_BMS',        '>l',  3, 4, 1E3],
                     ['battery_current_BMS',        '>l',  7, 4, 1E3],
                     ['high_cell_voltage',          '>L', 12, 4, 1E3],
                     ['low_cell_voltage',           '>L', 20, 4, 1E3],
                     ['high_battery_temp',          '>h', 34, 2, 1E1],
                     ['high_BMS_temp',              '>h', 40, 2, 1E1]]
            # poll
        self.uart.write(request)
        response = self.uart.read(packet_length)
        if response is not None:
            for ed in EBMS_data:
                key, format, start, length, scale = ed
                vehicle_data[key] = struct.unpack(format, response[start:start+length])[0]/scale


    def update_ZESC(self, vehicle_data):

        request = bytes([0x02, 0x03, 0x22, 0x01, 0x04, 0x9B, 0x13, 0x03])
        packet_length = 78

        ZESC_data = [['controller_temperature', '>h',  3, 2, 1E1],
                    ['motor_temperature',      '>h',  5, 2, 1E1],
                    ['motor_current',          '>l',  7, 4, 1E2],
                    ['battery_current',        '>l', 11, 4, 1E2],
                    ['motor_rpm',              '>l', 25, 4, 1E0],
                    ['battery_voltage',        '>h', 29, 2, 1E1]]

        self.uart.write(request)
        response = None
        response = self.uart.read(packet_length)
        # print(response)
        # poll

        if response is not None:
            for zd in ZESC_data:
                key, format, start, length, scale = zd
                vehicle_data[key] = struct.unpack(format, response[start:start+length])[0]/scale
        # if time out
        # if done

    def checksum(self):
        pass


console = CONSOLE()
canbus = CANBUS()
derived = DERIVED()
tft = TFT()
sdcard = SDCARD()
# uart = UART()


debug_pin = digitalio.DigitalInOut(board.D11)
debug_pin.direction = digitalio.Direction.OUTPUT

ready_to_calculate = True

print("ENNOID/VESC CAN reader")
while 1:
    ready_to_calculate = canbus.update_block(vehicle_data, ready_to_calculate)
    # uart.update(vehicle_data)
    derived.update(ready_to_calculate, strings)
    if sdcard.filename is not None:
        sdcard.update()
    # console.update()
    # debug_pin.value = True
    tft.update_line_by_line(strings)
    # tft.update_all(strings)
    # debug_pin.value = False