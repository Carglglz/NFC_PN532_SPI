
# Adapted from https://github.com/agama-point/micropython-ndeflib/blob/develop/src/ndef/microuri.py

from io import BytesIO


class MicroUri:
    _type = "urn:nfc:wkt:U"
    _prefix_strings = (
        "",
        "http://www.",
        "https://www.",
        "http://",
        "https://",
        "tel:",
        "mailto:",
        "ftp://anonymous:anonymous@",
        "ftp://ftp.",
        "ftps://",
        "sftp://",
        "smb://",
        "nfs://",
        "ftp://",
        "dav://",
        "news:",
        "telnet://",
        "imap:",
        "rtsp://",
        "urn:",
        "pop:",
        "sip:",
        "sips:",
        "tftp:",
        "btspp://",
        "btl2cap://",
        "btgoep://",
        "tcpobex://",
        "irdaobex://",
        "file://",
        "urn:epc:id:",
        "urn:epc:tag:",
        "urn:epc:pat:",
        "urn:epc:raw:",
        "urn:epc:",
        "urn:nfc:",
    )

    def __init__(self, BaseNDEFRecord, uri=None):
        self._baserecord = BaseNDEFRecord
        self.uri = uri if uri is not None else ""

    def __str__(self):
        """Return an informal representation suitable for printing."""
        return ("NDEF MicroUri ID '{}' URI: '{}'").format(self.name, self.uri)

    @property
    def uri(self):
        return self._url

    @uri.setter
    def uri(self, value):
        value = self._baserecord._value_to_unicode(value, "uri")
        self._url = value

    def _encode_payload(self):
        for prefix in self._prefix_strings:
            if prefix and self.uri.startswith(prefix):
                index = self._prefix_strings.index(prefix)
                return bytes([index]) + self.uri[len(prefix) :].encode()

        return b"\x00" + self.uri.encode()

    _decode_min_payload_length = 1
    _decode_max_payload_length = 512

    @classmethod
    def _decode_payload(cls, baserecord, octets):
        stream = BytesIO(octets)
        code = stream.read(1)[0]
        data = stream.read()

        return cls(baserecord, cls._prefix_strings[code].encode() + data)
