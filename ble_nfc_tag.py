# This example demonstrates a simple temperature sensor peripheral
# with Battery Service (Level and Power State)
#
# Connected Mode: The sensor's local value updates every 30 seconds
# When Battery Level is over 90 % or under 10 % it notifies the Central
# with the Battery Power State
#
# Save Energy Mode: To save Battery power,
# it will advertise for 30 seconds, if there is no connection
# event, it will enter into deep sleep for 60 seconds.
# If there is a connection event, it will enter the Connected Mode
# If there is a disconnection event, it will enter into Save Energy Mode

# Once BLE_Battery_Temp class is initiated it will enter the Save Energy Mode
# Battery Level and Temperature Values are an average of 30 previous samples

import bluetooth
import struct
import time
from ble_advertising import advertising_payload
from utag import NFCTag
from machine import unique_id, Timer, PWM, Pin, SPI
from micropython import const
from binascii import hexlify
import os
import sys
import NFC_PN532 as nfc


_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)


# org.bluetooth.service.enviromental_sensing
_USER_DATA_UUID = bluetooth.UUID(0x181C)


# org.bluetooth.characteristic.temperature
_USER_NAME_CHAR = (
    bluetooth.UUID(0x2A8A),
    bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY,
    # (_CHAR_USER_DESC,)
)


_USER_DATA_SERVICE = (
    _USER_DATA_UUID,
    (_USER_NAME_CHAR,),
)

# org.bluetooth.service.device_information
_DEV_INF_SERV_UUID = bluetooth.UUID(0x180A)
# org.bluetooth.characteristic.appearance
_APPEAR_CHAR = (
    bluetooth.UUID(0x2A01),
    bluetooth.FLAG_READ
)
# org.bluetooth.characteristic.manufacturer_name_string
_MANUFACT_CHAR = (
    bluetooth.UUID(0x2A29),
    bluetooth.FLAG_READ
)

# org.bluetooth.characteristic.gap.appearance
_ADV_APPEARANCE_GENERIC_TAG = const(512)

_MANUFACT_ESPRESSIF = const(741)

systeminfo = os.uname()
mn = hexlify(unique_id()).decode()
_SERIAL_NUMBER = ':'.join([mn[i:i+2].upper() for i in range(0, len(mn), 2)])
_MODEL_NUMBER = systeminfo.machine
_FIRMWARE_REV = "{}-{}".format(sys.implementation[0], systeminfo.release)
_HARDWARE_REV = systeminfo.sysname
_SOFTWARE_REV = sys.version

_MODEL_NUMBER_CHAR = (
        bluetooth.UUID(0x2A24),
        bluetooth.FLAG_READ)

_SERIAL_NUMBER_CHAR = (
        bluetooth.UUID(0x2A25),
        bluetooth.FLAG_READ)

_FIRMWARE_REV_CHAR = (
        bluetooth.UUID(0x2A26),
        bluetooth.FLAG_READ)

_HARDWARE_REV_CHAR = (
        bluetooth.UUID(0x2A27),
        bluetooth.FLAG_READ)

_SOFTWARE_REV_CHAR = (
        bluetooth.UUID(0x2A28),
        bluetooth.FLAG_READ)

_DEV_INF_SERV_SERVICE = (
    _DEV_INF_SERV_UUID,
    (_APPEAR_CHAR, _MANUFACT_CHAR, _MODEL_NUMBER_CHAR,
     _SERIAL_NUMBER_CHAR, _FIRMWARE_REV_CHAR,
     _HARDWARE_REV_CHAR, _SOFTWARE_REV_CHAR),
)

# SPI connection:
spi_dev = SPI(2, baudrate=1000000)
cs = Pin(14, Pin.OUT)
cs.on()
rst = Pin(5, Pin.OUT)

# SENSOR INIT
pn532 = nfc.PN532(spi_dev, cs, reset=rst)

ic, ver, rev, support = pn532.firmware_version
print('Found PN532 with firmware version: {0}.{1}'.format(ver, rev))

# Configure PN532 to communicate with MiFare cards
pn532.SAM_configuration()


class BLE_NFC:
    def __init__(self, ble, name="esp32-NFC", led=None, nfc_reader=pn532):

        self.NFC_timer = Timer(-1)

        self.led = led
        self.nfc_reader = nfc_reader
        self._nfc_tag = NFCTag(device=nfc_reader, init=False)
        # self.ads_dev.ads.conversion_start(7, channel1=self.ads_dev.channel)
        self.irq_busy = False
        self.buzz = PWM(Pin(25), freq=4000, duty=512)
        self.buzz.deinit()
        self.i = 0

        self.is_connected = False
        self._ble = ble
        self._ble.active(True)
        self._ble.config(gap_name='ESP32-NFC')
        self._ble.irq(self._irq)
        ((self._appear, self._manufact, self._model,
          self._serialn, self._firm, self._hardw, self._softw), (self._user,)) = self._ble.gatts_register_services(
            (_DEV_INF_SERV_SERVICE, _USER_DATA_SERVICE,))
        self._connections = set()
        self._payload = advertising_payload(
            name=name, services=[
                _USER_DATA_UUID], appearance=_ADV_APPEARANCE_GENERIC_TAG
        )
        self._advertise()
        self._ble.gatts_write(self._appear, struct.pack(
            "h", _ADV_APPEARANCE_GENERIC_TAG))
        self._ble.gatts_write(self._manufact, bytes('Espressif Incorporated',
                                                    'utf8'))
        self._ble.gatts_write(self._model, bytes(_MODEL_NUMBER, 'utf8'))
        self._ble.gatts_write(self._serialn, bytes(_SERIAL_NUMBER, 'utf8'))
        self._ble.gatts_write(self._firm, bytes(_FIRMWARE_REV, 'utf8'))
        self._ble.gatts_write(self._hardw, bytes(_HARDWARE_REV, 'utf8'))
        self._ble.gatts_write(self._softw, bytes(_SOFTWARE_REV, 'utf8'))
        # self._ble.gatts_write(self._char_userdesc, bytes('ESP32 CPU Temperature',
        #                                                  'utf8'))
        for i in range(5):
            for k in range(4):
                self.led.value(not self.led.value())
                time.sleep(0.2)
            time.sleep(0.5)

    def _irq(self, event, data):
        self.irq_busy = True
        # Track connections so we can send notifications.
        # print('event: {}'.format(event))
        if event == _IRQ_CENTRAL_CONNECT:
            print('Central Connected')
            conn_handle, _, _, = data
            self._connections.add(conn_handle)
            self.is_connected = True
            self.buzz_beep(150, 2, 100, 4000)
            self.stop_sense_nfc()
            self.start_sense_nfc()
        elif event == _IRQ_CENTRAL_DISCONNECT:
            print('Central Disconnected')
            self.stop_sense_nfc()
            conn_handle, _, _, = data
            self.is_connected = False
            self._connections.remove(conn_handle)
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle, = data
        self.irq_busy = False

    def buzz_beep(self, beep_on_time=150, n_times=2, beep_off_time=100, fq=4000,
                  led=True):
        self.buzz.freq(fq)
        if led:
            for i in range(n_times):
                self.buzz.init()
                self.led.on()
                time.sleep_ms(beep_on_time)
                self.buzz.deinit()
                self.led.off()
                time.sleep_ms(beep_off_time)
        else:
            for i in range(n_times):
                self.buzz.init()
                time.sleep_ms(beep_on_time)
                self.buzz.deinit()
                time.sleep_ms(beep_off_time)

    def read_nfc_tag(self):

        uid = self.nfc_reader.read_passive_target(timeout=500)
        if uid:
            if not self._nfc_tag.mad.NFCSectors:
                self._nfc_tag.get_info()
            if self._nfc_tag.read_nfc_records(n=1, debug=True, on_detect=self.buzz_beep,
                                              at_end=self.buzz_beep, checked_tag=True,
                                              uid=uid):
                self._ble.gatts_write(self._user, self._nfc_tag.NFCRecords['r0'].text.encode())

                for conn_handle in self._connections:
                    self._ble.gatts_notify(conn_handle, self._user)

    def _advertise(self, interval_us=500000):
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

    def read_nfc_callback(self, x):
        if self.irq_busy:
            return
        else:
            if not self.is_connected:
                self.stop_sense_nfc()
                return
            try:
                self.irq_busy = True
                self.read_nfc_tag()
                time.sleep_ms(500)
                self.irq_busy = False
            except Exception as e:
                print(e)
                self.irq_busy = False

    def start_sense_nfc(self, timeout=1000):
        self.irq_busy = False
        self.NFC_timer.init(period=timeout, mode=Timer.PERIODIC,
                            callback=self.read_nfc_callback)

    def stop_sense_nfc(self):
        self.NFC_timer.deinit()
        self.irq_busy = False
