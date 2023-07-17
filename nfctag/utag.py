# https://learn.adafruit.com/adafruit-pn532-rfid-nfc/mifare

# EEPROM Memory Mifare Classic

# 1k --> 1024 bytes | 16 Sectors | 4 Blocks per Sector (64 bytes) --> 1 Block 16 bytes
# 4k --> 4096 bytes | 32 sectors of 4 blocks each + 8 sectors of 16 blocks each --> 1 Block 16 bytes

#
# Sector  Block   Bytes                                                           Description
#   ------  -----   -----                                                           -----------
#                   0   1   2   3   4   5   6   7   8   9   10  11  12  13  14  15
#    0      0       [                     Manufacturer Data                     ]   Manufacturer Block
#           1       [                            Data                           ]   Data
#           2       [                            Data                           ]   Data
#           3       [-------KEY A-------]   [Access Bits]   [-------KEY B-------]   Sector Trailer
#
#
#    1      4       [                            Data                           ]   Data
#           5       [                            Data                           ]   Data
#           6       [                            Data                           ]   Data
#           7       [-------KEY A-------]   [Access Bits]   [-------KEY B-------]   Sector Trailer
#
#   .
#   .
#   .
#
#    15    60       [                            Data                           ]   Data
#          61       [                            Data                           ]   Data
#          62       [                            Data                           ]   Data
#          63       [-------KEY A-------]   [Access Bits]   [-------KEY B-------]   Sector Trailer
#
#

import struct
from binascii import hexlify
from uNDEF import NDEFRecord
import gc
import io

_NDEF_Message = b"\x03"
_NDEF_Terminator = b"\xfe"
_NDEF_Terminator_int = 0xFE
_MAD_AID_NFC = 0xE103
_BB = "\u001b[34;1m{}\u001b[0m"
_BG = "\u001b[32;1m{}\u001b[0m"
_BM = "\u001b[35;1m{}\u001b[0m"
_BY = "\u001b[33;1m{}\u001b[0m"
_KLHXFM = 7 * 2 + 4

# TODO: switch io.BytesIO for memory, improve memory allocation --> close to 0
# at runtime


class NFCTag:
    def __init__(self, memory_size=1024, uid=b"", device=None, init=True):
        """ "Class to read Mifare Classic NFC Cards/Tags with NDEF Messages/Records
        memory_size = 1024 --> 1k Cards/Tags
        device = PN532 class
        """
        # (16 sectors/card x 3 data blocks/sector X 16 bytes/block) -- 16 bytes
        # (first block) = 752 bytes/card
        self._memory = bytearray(memory_size)
        self._buffer_memory = memoryview(self._memory)
        self._payload_mem = io.BytesIO(752)
        self._payload_buff = bytearray(752)
        self._nsectors = 16
        self._nblocks = 64
        self._blen = 16
        self._bps = 4
        self._uid = uid
        self._device = device
        self._memdumped = False
        if self._device:
            self._device.auth_key = "NFCS"  # NFC Sector Key
        self._manufacturer = b""
        self._wr_sectors = []
        self._NFC_records = {}

        self._blocks = {
            i: self._buffer_memory[
                i * self._nsectors : (i * self._nsectors) + self._nsectors
            ]
            for i in range(0, self._nblocks)
        }
        self._sectors = {
            i: [
                self._blocks[k]
                for k in range(i * self._bps, (i * self._bps) + self._bps)
            ]
            for i in range(self._nsectors)
        }

        self._mad = MAD1(self._blocks[1] + self._blocks[2])

        self._nfc_payload = bytearray()
        if init:
            self.get_info()

    def __repr__(self):
        print("NFCTag")
        print("Memory: {} bytes".format(len(self._memory)))
        print("UID: {}".format(hexlify(self._uid, ":").decode()))
        print("Manufacturer: {}".format(hexlify(self._manufacturer, ":").decode()))
        if sum(self._blocks[1]) != 0:
            print("MAD1 PRESENT")
        else:
            print("EMPTY MAD")
        self._pprintmemdump()
        return "--- END ---"

    def get_info(self):
        self.get_uid()
        self.get_manufacturer()
        self.get_block(1)
        self.get_block(2)
        self._mad.set_mad_data(self.block(1) + self.block(2))

    def block(self, number):
        return bytes(self._blocks[number])

    def sector(self, number):
        return {
            number * self._bps + i: bytes(self._sectors[number][i])
            for i in range(self._bps)
        }

    def check_tag(self):
        if self._device:
            self.get_uid()
            auth = self._device.mifare_classic_authenticate_block(self.uid, 4)
            if auth:
                if self._device.auth_key == "NFCS":
                    print("NFC formatted Tag")
                elif self._device.auth_key == "DEF":
                    print("EMPTY NFC Format")
            else:
                if self._device.auth_key == "NFCS":
                    self._device.auth_key = "DEF"
                else:
                    self._device.auth_key = "NFCS"
                self.get_uid()
                auth = self._device.mifare_classic_authenticate_block(self.uid, 4)
                if auth:
                    if self._device.auth_key == "NFCS":
                        print("NFC formatted Tag")
                    elif self._device.auth_key == "DEF":
                        print("EMPTY NFC Format")
                else:
                    print("Unkown NFC formatted Tag, key UNKNOWN")

    @property
    def manufacturer(self):
        return self._manufacturer

    def get_manufacturer(self):
        if self._device:
            data = self._device.read_mifare_classic(0)
            if data:
                self._manufacturer = data
                if len(data) == self._blen:
                    self._blocks[0][:] = data

    @property
    def uid(self):
        return self._uid

    def get_uid(self, ret=False):
        if self._device:
            uid = self._device.read_passive_target()
            if uid:
                self._uid = uid
            if ret:
                return uid

    @property
    def mad(self):
        return self._mad

    def get_mad(self):
        if self._device:
            mad_data = bytes()
            mad_data += self.block(1)
            mad_data += self.block(2)
            self._mad.set_mad_data(mad_data)

    def is_st(self, n):
        return n in (i for i in range(3, 64, 4))

    def _pprintmemdump(self):
        n = 0
        for sector in self._sectors:
            if sector == 0:
                print("-" * 5, "Sector {}".format(sector), "-" * 5)
                for block in self._sectors[sector]:
                    if block == self._sectors[sector][0]:
                        print(
                            "Block {}: {}".format(
                                n, _BB.format(hexlify(bytes(block), " ").decode())
                            )
                        )
                    elif (
                        block == self._sectors[sector][1]
                        or block == self._sectors[sector][2]
                    ):
                        print(
                            "Block {}: {}".format(
                                n, _BM.format(hexlify(bytes(block), " ").decode())
                            )
                        )
                    else:
                        bl = hexlify(bytes(block), " ").decode()
                        if self._device and self._memdumped is True:
                            if self._device.auth_key == "NFCS":
                                keyA = (
                                    _BG.format(
                                        hexlify(
                                            self._device.mifare_keys["MAD"], " "
                                        ).decode()
                                    )
                                    + " "
                                )
                                keyB = " " + _BY.format(
                                    hexlify(self._device._auth_key, " ").decode()
                                )
                            else:
                                keyA = _BG.format(bl[:_KLHXFM])
                                keyB = _BY.format(bl[-_KLHXFM:])
                            Staddr = bl[_KLHXFM:-_KLHXFM]
                            print("Block {}: {}{}{}".format(n, keyA, Staddr, keyB))
                        else:
                            print("Block {}: {}".format(n, bl))
                    n += 1
            else:
                print("-" * 5, "Sector {}".format(sector), "-" * 5)
                for block in self._sectors[sector]:
                    if block == self._sectors[sector][-1]:
                        bl = hexlify(bytes(block), " ").decode()
                        if self._device and self._memdumped is True:
                            if self._device.auth_key == "NFCS":
                                keyA = (
                                    _BG.format(
                                        hexlify(self._device._auth_key, " ").decode()
                                    )
                                    + " "
                                )
                                keyB = " " + _BY.format(
                                    hexlify(self._device._auth_key, " ").decode()
                                )
                            else:
                                keyA = _BG.format(bl[:_KLHXFM])
                                keyB = _BY.format(bl[-_KLHXFM:])
                            Staddr = bl[_KLHXFM:-_KLHXFM]
                            print("Block {}: {}{}{}".format(n, keyA, Staddr, keyB))
                        else:
                            print("Block {}: {}".format(n, bl))
                    else:
                        print(
                            "Block {}: {}".format(
                                n, hexlify(bytes(block), " ").decode()
                            )
                        )
                    n += 1

        return ""

    def memorydump(self, debug=False, rtn=False):
        if self._device:
            if debug:
                print("Reading NFC Tag...")
            for block in range(self._nblocks):
                block_data = self._device.read_mifare_classic(block, debug=debug)
                if debug:
                    print(
                        "[{:80}] {} %\r".format(
                            int((block / self._nblocks) * 80) * "#",
                            int((block / self._nblocks) * 100),
                        ),
                        end="",
                    )
                if block_data:
                    self._memory[
                        block * self._blen : (block * self._blen) + self._blen
                    ] = block_data

            self.get_mad()
            if debug:
                print(
                    "[{:80}] {} %\r".format(
                        int(((block + 1) / self._nblocks) * 80) * "#",
                        int(((block + 1) / self._nblocks) * 100),
                    )
                )
                print("Done!")

            self._memdumped = True
            if rtn:
                return bytes(self._buffer_memory)

    def get_sector(
        self,
        number,
        byblocks=False,
        debug=False,
        checked_tag=False,
        on_detect=None,
        on_reading=None,
        at_end=None,
        cache=False,
        skip_st=False,
        rtn=True,
        **kwargs,
    ):
        if number > self._nsectors - 1:
            raise IndexError
        if self._device and not cache:
            uid = kwargs.get("uid")
            if uid:
                kwargs.pop("uid")
            if not checked_tag:
                checked_tag = self._device.read_passive_target()
            if checked_tag:
                if on_detect:
                    on_detect(**kwargs)
                for block in range(self._bps):
                    if on_reading:
                        on_reading(**kwargs)
                    b_index = (number * self._bps) + block

                    if skip_st and self.is_st(b_index):
                        continue
                    block_data = self._device.read_mifare_classic(
                        b_index, debug=debug, uid=uid
                    )
                    if debug:
                        print(f"Block: {b_index}; DATA: {block_data}")
                    if block_data:
                        self._blocks[b_index][:] = block_data
                if at_end:
                    at_end(**kwargs)
        if byblocks:
            return self.sector(number)
        else:
            if rtn:
                sector = bytes()
                for nb, block in enumerate(self.sector(number).values()):
                    if skip_st and self.is_st(nb):
                        break
                    sector += block
                return sector

    def get_block(self, number, debug=False):
        if number > self._nblocks - 1:
            raise IndexError
        if self._device:
            block_data = self._device.read_mifare_classic(number, debug=debug)
            if block_data and len(block_data) == self._blen:
                self._blocks[number][:] = block_data

        return self.block(number)

    def find_wr_sectors(
        self, nfcfilter=True, stop_at_first_empty=False, debug=False, cache=False
    ):
        # Check if sector is not empty
        # Read first block of each sector
        # Up to 1st non-empty, or all
        # Filter by NFC only (using mad data)3
        wr_sectors = []
        for bl in range(self._bps, self._nblocks, self._bps):
            sector = int(bl / self._bps)

            if cache:
                nb = self.block(bl)
            else:
                nb = self.get_block(bl, debug=debug)
            if sum(nb) != 0:
                wr_sectors.append(sector)

            else:
                if stop_at_first_empty:
                    break

        self._wr_sectors = wr_sectors

        if nfcfilter:
            self._wr_sectors = [sec for sec in wr_sectors if sec in self.mad.NFCSectors]
            return self._wr_sectors
        else:
            return self._wr_sectors

    def find_tlvblock(
        self,
        datablock,
        debug=False,
    ):
        if isinstance(datablock, io.BytesIO):
            datablock.seek(0)
            dlen = 0
            si = 0
            while True:
                bd = datablock.read(1)
                si += 1
                if bd != _NDEF_Message:
                    continue
                else:
                    dlen = datablock.read(1)
                    # len format
                    if ord(dlen) < 0xFF:
                        dlen = ord(dlen)
                        datablock.readinto(self._payload_buff, dlen)
                    else:
                        (dlen,) = struct.unpack(">H", datablock.read(2))
                        datablock.readinto(self._payload_buff, dlen)

                    ender = datablock.read(1)
                    assert ender == _NDEF_Terminator, "Block ender missmatch"
                    return dlen

        else:
            ndef_msg_start = datablock.index(_NDEF_Message)
            ndef_msg_end = datablock.index(_NDEF_Terminator)
            tlv_len_index = ndef_msg_start + 1
            tlv_len = datablock[tlv_len_index]
            bl_start = tlv_len_index + 1
            bl_end = bl_start + tlv_len
            tlv_block = datablock[tlv_len_index + 1 : bl_end]
        assert bl_end == ndef_msg_end, "Block ender index missmatch"
        assert datablock[bl_end] == _NDEF_Terminator_int, "Block ender index missmatch"
        if debug:
            print("NDEF Message with length {} found".format(tlv_len))
        return tlv_block

    def read_nfc_records(self, n=None, debug=False, cache=False, **kwargs):
        # SECTORS :
        raw_records = {}
        ri = 0
        if not n:
            if debug:
                print("Looking for written sectors...")
            nfc_nonempty_sectors = self.find_wr_sectors(
                stop_at_first_empty=True, debug=debug, cache=cache
            )
            if debug:
                print("Found {} written sectors".format(nfc_nonempty_sectors))
        else:
            nfc_nonempty_sectors = [1]
        for nfcs in nfc_nonempty_sectors:
            if debug:
                print(f"Sector {nfcs}")
            self.get_sector(
                nfcs, debug=debug, cache=cache, skip_st=True, rtn=False, **kwargs
            )

            self._payload_mem.seek(0)
            for i in nfc_nonempty_sectors:
                for j in range(self._bps - 1):
                    self._payload_mem.write(self._sectors[i][j])
        dlen = self.find_tlvblock(self._payload_mem)
        record = NDEFRecord(self._payload_buff[:dlen])
        while True:
            try:
                raw_records["r{}".format(ri)], *_ = record._decode()
                ri += 1
            except TypeError:
                break
            except Exception as e:
                raise e
        if debug:
            print("{} Records found".format(len(raw_records)))

        self._NFC_records = raw_records
        gc.collect()
        return self.NFCRecords

    @property
    def NFCRecords(self):
        return self._NFC_records


#  Using Mifare Classic Cards as an NDEF Tag #

# Mifare Application Directory (MAD)
# ----------------------------------
# In order to form a relationship between the sector-based memory of a Mifare Classic
# card and the individual NDEF records, the Mifare Application Directory (MAD) structure
# is used. The MAD indicates which sector(s) contains which NDEF record
# MAD1 can be used in any Mifare Classic card regardless of the size of the EEPROM,
# although if it is used with cards larger than 1KB only the first 1KB of memory will
# be accessible for NDEF records.


class MAD1:
    """
    Mifare Application Directory 1 (MAD1)
    The MAD1 is stored in the Manufacturer Sector (Sector 0x00) on the
    Mifare Classic card.
    The MAD indicates which sector(s) contains which NDEF record
    """

    def __init__(self, madblocks=None):
        self._mad = madblocks
        self._nfc_sectors = []
        if madblocks:
            self._crc = self._mad[0]  # CRC
            self._info = self._mad[1]  # INFO
            self._aids = dict(
                zip(
                    [k for k in range(1, 16)],
                    [self._mad[i : i + 2] for i in range(2, 32, 2)],
                )
            )
            self._get_nfc_sectors()

    def __repr__(self):
        if self._mad:
            print("--- MAD1 ---")
            print("CRC: {}".format(hex(self._crc)))
            print("INFO: {}".format(hex(self._info)))
            for sec_index, aid in self._aids.items():
                if sec_index in self._nfc_sectors:
                    print(
                        "AID{} : 0x{} [NFC SECTOR]".format(
                            sec_index, hexlify(aid).decode()
                        )
                    )
                else:
                    print("AID{} : {}".format(sec_index, hexlify(aid).decode()))
            return "--- END ---"

    @property
    def NFCSectors(self):
        if self._aids:
            self._get_nfc_sectors()
        return self._nfc_sectors

    def _get_nfc_sectors(self):
        self._nfc_sectors = []
        for sec_index, aid in self._aids.items():
            aid_code = 0
            try:
                (aid_code,) = struct.unpack("H", aid)
            except Exception:
                print(aid)
            if aid_code == _MAD_AID_NFC:
                self._nfc_sectors.append(sec_index)

    def set_mad_data(self, data):
        self._mad = data
        self._crc = self._mad[0]  # CRC
        self._info = self._mad[1]  # INFO
        self._aids = dict(
            zip(
                [k for k in range(1, 16)],
                [self._mad[i : i + 2] for i in range(2, 32, 2)],
            )
        )
        self._get_nfc_sectors()

    # GET NDEF MESSAGE
    # GET NDEF RECORD
    # DECODE NDEF RECORD
