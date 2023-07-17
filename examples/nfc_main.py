# @Author: carlosgilgonzalez
# @Date:   2019-03-12T00:13:53+00:00
# @Last modified by:   carlosgilgonzalez
# @Last modified time: 2019-07-05T18:49:15+01:00

from machine import Pin
from ble_nfc_tag import BLE_NFC
import bluetooth

ble = bluetooth.BLE()
# LED
led = Pin(13, Pin.OUT)
blenfc = BLE_NFC(ble, led=led)
