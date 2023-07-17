# Notes from : https://learn.adafruit.com/adafruit-pn532-rfid-nfc/ndef

# NDEF Messages
# --------------

# NDEF Messages are the basic "transportation" mechanism for NDEF records,
# with each message containing one or more NDEF Records.

# NDEF Records
# ------------
# NDEF Records contain a specific payload, and have the following structure that
# identifies the contents and size of the record:


# Byte    Bit 7     6       5       4       3       2       1       0
#         ------  ------  ------  ------  ------  ------  ------  ------
# 0       [ MB ]  [ ME ]  [ CF ]  [ SR ]  [ IL ]  [        TNF         ]
#
# 1       [                         TYPE LENGTH                        ]
#
# 2       [                       PAYLOAD LENGTH                       ]
#
# 3       [                          ID LENGTH                         ]
#
# 4       [                         RECORD TYPE                        ]
#
# 5       [                              ID                            ]
#
# 6       [                           PAYLOAD                          ]
# .
# .
# .
# N       [                           PAYLOAD                          ]

# Record Header (Byte 0)
# ----------------------
# TNF: Type Name Format Field
# ---------------------------
# The Type Name Format or TNF Field of an NDEF record is a 3-bit value that describes
# the record type, and sets the expectation for the structure and content of the rest
# of the record


#   TNF Value    Record Type
#   ---------    -----------------------------------------
#   0x00         Empty Record
#                Indicates no type, id, or payload is associated with this NDEF Record.
#                This record type is useful on newly formatted cards since every NDEF
#                tag must have at least one NDEF Record.

#   0x01         Well-Known Record
#                Indicates the type field uses the RTD type name format.
#                This type name is used to stored any record defined by a Record Type
#                Definition (RTD), such as storing
#                RTD Text, RTD URIs, etc., and is one of the mostly frequently used and
#                useful record types.

#   0x02         MIME Media Record
#                Indicates the payload is an intermediate or final chunk of a chunked
#                NDEF Record

#   0x03         Absolute URI Record
#                Indicates the type field contains a value that follows the absolute-URI
#                BNF construct defined by RFC 3986

#   0x04         External Record
#                Indicates the type field contains a value that follows the RTD external
#                name specification

#   0x05         Unknown Record
#                Indicates the payload type is unknown

#   0x06         Unchanged Record
#                Indicates the payload is an intermediate or final chunk of a chunked
#                NDEF Record

# IL: ID LENGTH Field
# -------------------
# The IL flag indicates if the ID Length Field is preent or not. If this is set to 0,
# then the ID Length Field is ommitted in the record.

# SR: Short Record Bit
# -------------------
# The SR flag is set to one if the PAYLOAD LENGTH field is 1 byte (8 bits/0-255) or
# less. This allows for more compact records.

# CF: Chunk Flag
# -------------------
# The CF flag indicates if this is the first record chunk or a middle record chunk.

# ME: Message End
# -------------------
# The ME flag indicates if this is the last record in the message.

# MB: Message Begin
# --------------------
# The MB flag indicates if this is the start of an NDEF message


# Type Length
# -----------
# Indicates the length (in bytes) of the Record Type field. This value is always zero
# for certain types of records defined with the TNF Field described above.

# Payload Length
# --------------
# Indicates the length (in bytes) of the record payload. If the SR field
# (described above) is set to 1 in the record header, this value will be one byte long
# (for a payload length from 0-255 bytes).
# If the SR field is set to 0, this value will be a 32-bit value occupying 4 bytes.

# ID Length
# ---------
# Indicates the length in bytes of the ID field. This field is present only if the IL
# flag (described above) is set to 1 in the record header.

# Record Type
# -----------
# This value describes the 'type' of record that follows. The values of the type field
# must corresponse to the value entered in the TNF bits of the record header.

# Record ID
# ---------
# The value of the ID field if an ID is included (the IL bit in the record header is
# set to 1). If the IL bit is set to 0, this field is ommitted.

# Payload
# -------
# The record payload, which will be exactly the number of bytes described in the
# Payload Length field earlier.

import struct
import io
from ndeftext import NDEFTextRecord
from ndefuri import MicroUri


class NDEFdecodeError(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return "NDEFdecodeError: {0} ".format(self.message)
        else:
            return "NDEFdecodeError"


class NDEFRecordHeader:
    def __init__(self, tnf, il, sr, cf, me, mb):
        self._TNF = tnf  # Type Name Format Field
        self._IL = il  # ID LENGTH Field
        self._SR = sr  # Short Record Bit
        self._CF = cf  # Chunk Flag
        self._ME = me  # Message End
        self._MB = mb  # Message Begin


class NDEFRecord:
    def __init__(self, stream_or_bytes):
        """ "
        NDEF Records contain a specific payload
        """
        if isinstance(stream_or_bytes, (io.IOBase)):
            stream = stream_or_bytes
        elif isinstance(stream_or_bytes, (bytes, bytearray)):
            stream = io.BytesIO(stream_or_bytes)
        else:
            errstr = "a stream or bytes type argument is required, not {}"
            raise TypeError(errstr.format(type(stream_or_bytes).__name__))

        self._data = stream
        self._header = bytearray(1)
        self.header = 0
        self._typelen = 0
        self._payloadlen = 0
        self._idlen = 0
        self._record_type = 0
        self._record_id = 0
        self._payload = bytes()
        self.MAX_PAYLOAD_SIZE = 512
        self.known_types = {
            NDEFTextRecord._type: NDEFTextRecord,
            MicroUri._type: MicroUri,
        }
        self._decode_min_payload_length = 1
        self._decode_max_payload_length = 512

    def _decode(self):
        try:
            octet0 = ord(self._data.read(1))
        except IndexError:
            return (None, False, False, False)

        MB = bool(octet0 & 0b10000000)
        ME = bool(octet0 & 0b01000000)
        CF = bool(octet0 & 0b00100000)
        SR = bool(octet0 & 0b00010000)
        IL = bool(octet0 & 0b00001000)
        TNF = octet0 & 0b00000111
        self.header = NDEFRecordHeader(TNF, IL, SR, CF, ME, MB)

        if TNF == 7:
            raise self._decode_error("TNF field value must be between 0 and 6")

        try:
            structfmt = ">B" + ("B" if SR else "L") + ("B" if IL else "")
            data = self._data.read(struct.calcsize(structfmt))
            fields = struct.unpack(structfmt, data) + (0,)
        except Exception as e:
            errstr = "buffer underflow at reading length fields"
            raise self._decode_error(errstr)

        try:
            if TNF in (0, 5, 6):
                assert fields[0] == 0, "TYPE_LENGTH must be 0"
            if TNF == 0:
                assert fields[2] == 0, "ID_LENGTH must be 0"
                assert fields[1] == 0, "PAYLOAD_LENGTH must be 0"
            if TNF in (1, 2, 3, 4):
                assert fields[0] > 0, "TYPE_LENGTH must be > 0"
        except AssertionError as error:
            raise self._decode_error(str(error) + " for TNF value {}", TNF)

        if fields[1] > self.MAX_PAYLOAD_SIZE:
            errstr = "payload of more than {} octets can not be decoded"
            raise self._decode_error(errstr.format(self.MAX_PAYLOAD_SIZE))

        TYPE, ID, PAYLOAD = [self._data.read(fields[i]) for i in (0, 2, 1)]

        try:
            assert fields[0] == len(TYPE), "TYPE field"
            assert fields[2] == len(ID), "ID field"
            assert fields[1] == len(PAYLOAD), "PAYLOAD field"
        except AssertionError as error:
            raise self._decode_error("buffer underflow at reading {}", error)

        record_type = self._decode_type(TNF, TYPE)
        if record_type in self.known_types:
            record_cls = self.known_types[record_type]
            min_payload_length = record_cls._decode_min_payload_length
            max_payload_length = record_cls._decode_max_payload_length
            if len(PAYLOAD) < min_payload_length:
                errstr = "payload length can not be less than {}"
                # raise record_cls._decode_error(errstr, min_payload_length)
                print(errstr)
            if len(PAYLOAD) > max_payload_length:
                errstr = "payload length can not be more than {}"
                # raise record_cls._decode_error(errstr, max_payload_length)
                print(errstr)
            record = record_cls._decode_payload(self, PAYLOAD)
            # record = PAYLOAD
            # assert isinstance(record, NDEFRecord)
            # record.name = ID
        else:
            record = "?"

        return (record, MB, ME, CF)

    def _decode_type(self, TNF, TYPE):
        # Convert an NDEF Record TNF and TYPE to a record type
        # string. For TNF 1 and 4 the record type string is a prexix
        # plus TYPE, for TNF 0, 5, and 6 it is a fixed string, for TNF
        # 2 and 3 it is directly the TYPE string. Other TNF values are
        # not allowed.
        prefix = ("", "urn:nfc:wkt:", "", "", "urn:nfc:ext:", "unknown", "unchanged")
        if not 0 <= TNF <= 6:
            raise self._value_error("NDEF Record TNF values must be 0 to 6")
        if TNF in (0, 5, 6):
            TYPE = b""
        return prefix[TNF] + (TYPE.decode())

    def _decode_struct(self, fmt, octets, offset=0, always_tuple=False):
        #
        assert fmt[0] not in ("@", "=", "!"), "only '>' and '<' are allowed"
        assert fmt.count("*") < 2, "only one '*' expression is allowed"
        assert "*" not in fmt or fmt.find("*") > fmt.rfind("+")
        order, fmt = (fmt[0], fmt[1:]) if fmt[0] in (">", "<") else (">", fmt)
        try:
            values = list()
            this_fmt = fmt
            while this_fmt:
                this_fmt, plus_fmt, next_fmt = this_fmt.partition("+")
                if "*" in this_fmt:
                    this_fmt, next_fmt = this_fmt.split("*", 1)
                    if this_fmt:
                        next_fmt = "*" + next_fmt
                    elif next_fmt:
                        trailing = len(octets) - offset
                        size_fmt = struct.calcsize(next_fmt)
                        this_fmt = int(trailing / size_fmt) * next_fmt
                        next_fmt = "*" if trailing % size_fmt else ""
                    else:
                        this_fmt = str(len(octets) - offset) + "s"
                        next_fmt = ""
                structfmt = order + this_fmt
                values = values + list(struct.unpack_from(structfmt, octets, offset))
                offset = offset + struct.calcsize(structfmt)
                if plus_fmt:
                    if next_fmt.startswith("("):
                        this_fmt, next_fmt = next_fmt[1:].split(")", 1)
                        structfmt = order + values.pop() * this_fmt
                        values.append(struct.unpack_from(structfmt, octets, offset))
                        offset = offset + struct.calcsize(structfmt)
                    else:
                        structfmt = "{:d}s".format(values.pop())
                        values.extend(struct.unpack_from(structfmt, octets, offset))
                        offset = offset + struct.calcsize(structfmt)
                this_fmt = next_fmt
        except Exception as error:
            raise self._decode_error(str(error))
        else:
            if len(values) == 1 and not always_tuple:
                return values[0]
            else:
                return tuple(values)

    def _decode_error(self, excpstr, excp=None):
        if excp:
            try:
                excpstr = excpstr.format(str(excp))
            except Exception as e:
                pass
        return NDEFdecodeError(excpstr)

    def _value_error(self, fmt, *args, **kwargs):
        # Return a ValueError instance with a formatted error string.
        # The error string starts with module and class name. The
        # formatted string fmt is joined with a '.' if the first word
        # of fmt is the name of a non-function class attribute,
        # otherwise it is joined with ' '.
        record = "NDEFRecord"
        joinby = ": "
        return ValueError(record + joinby + fmt.format(*args, **kwargs))

    def _value_to_unicode(self, value, name):
        try:
            if isinstance(value, (str, bytes)):
                return value if isinstance(value, str) else value.decode("ascii")
            if isinstance(value, bytearray):
                return value.decode("ascii")
        except UnicodeError:
            errstr = name + " conversion requires ascii text, but got {!r}"
            raise self._value_error(errstr, value)
