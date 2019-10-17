## MicroPython - PN532 NFC/RFID DRIVER (SPI)

MicroPython SPI driver for the [PN532 NFC/RFID Breakout](https://www.adafruit.com/product/364) and [PN532 NFC/RFID Shield](https://www.adafruit.com/product/789) (port from [CircuitPython driver](https://github.com/adafruit/Adafruit_CircuitPython_PN532) )



### Example:

```
import NFC_PN532 as nfc
from machine import Pin, SPI

# SPI
spi_dev = SPI(1, baudrate=1000000)
cs = Pin(5, Pin.OUT)
cs.on()

# SENSOR INIT
pn532 = nfc.PN532(spi_dev,cs)
ic, ver, rev, support = pn532.get_firmware_version()
print('Found PN532 with firmware version: {0}.{1}'.format(ver, rev))

# Configure PN532 to communicate with MiFare cards
pn532.SAM_configuration()

# FUNCTION TO READ 
def read_nfc(dev, tmot):
    """Accepts a device and a timeout in millisecs """
    print('Reading...')
    uid = dev.read_passive_target(timeout=tmot)
    if uid is None:
        print('CARD NOT FOUND')
    else:
        numbers = [i for i in uid]
        string_ID = '{}-{}-{}-{}'.format(*numbers)
        print('Found card with UID:', [hex(i) for i in uid])
        print('Number_id: {}'.format(string_ID))


read_nfc(pn532, 500)
Reading...
Found card with UID: ['0x0', '0xa', '0x33', '0xc0']
Number_id: 0-10-51-192
```



### Datasheet:

**[PN532](https://www.nxp.com/docs/en/nxp/data-sheets/PN532_C1.pdf)**

### User Manual:

**[PN532 User Manual](https://www.nxp.com/docs/en/user-guide/141520.pdf)** 