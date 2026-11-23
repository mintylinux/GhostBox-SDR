"""Small synchronous librtlsdr interface; no kernel driver or bias-tee changes."""

import ctypes as ct
import ctypes.util
import time

import numpy as np

IQ_RATE = 1_200_000
BLOCK_SAMPLES = 24_576  # 20.48 ms; USB reads must be multiples of 512 bytes.


def load_library():
    path = ctypes.util.find_library("rtlsdr")
    if not path:
        raise RuntimeError("librtlsdr is missing. Install rtl-sdr (see README).")
    lib = ct.CDLL(path)
    signatures = {
        "rtlsdr_get_device_count": ([], ct.c_uint32),
        "rtlsdr_get_device_name": ([ct.c_uint32], ct.c_char_p),
        "rtlsdr_open": ([ct.POINTER(ct.c_void_p), ct.c_uint32], ct.c_int),
        "rtlsdr_close": ([ct.c_void_p], ct.c_int),
        "rtlsdr_set_sample_rate": ([ct.c_void_p, ct.c_uint32], ct.c_int),
        "rtlsdr_set_center_freq": ([ct.c_void_p, ct.c_uint32], ct.c_int),
        "rtlsdr_set_tuner_gain_mode": ([ct.c_void_p, ct.c_int], ct.c_int),
        "rtlsdr_reset_buffer": ([ct.c_void_p], ct.c_int),
        "rtlsdr_read_sync": (
            [ct.c_void_p, ct.c_void_p, ct.c_int, ct.POINTER(ct.c_int)],
            ct.c_int,
        ),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(lib, name)
        fn.argtypes = args
        fn.restype = result
    return lib


def devices():
    lib = load_library()
    return [
        (i, lib.rtlsdr_get_device_name(i).decode(errors="replace"))
        for i in range(lib.rtlsdr_get_device_count())
    ]


class RtlSource:
    def __init__(self, device=0):
        self.lib = load_library()
        self.handle = ct.c_void_p()
        self.buffer = (ct.c_ubyte * (BLOCK_SAMPLES * 2))()
        if not 0 <= device < self.lib.rtlsdr_get_device_count():
            raise RuntimeError("RTL-SDR not found. Check USB connection and --device.")
        result = self.lib.rtlsdr_open(ct.byref(self.handle), device)
        if result < 0:
            raise RuntimeError(
                f"Cannot open RTL-SDR ({result}). Close other SDR apps and check USB permissions."
            )
        try:
            self._check(self.lib.rtlsdr_set_sample_rate(self.handle, IQ_RATE), "sample rate")
            self._check(self.lib.rtlsdr_set_tuner_gain_mode(self.handle, 0), "automatic gain")
        except Exception:
            self.close()
            raise

    @staticmethod
    def _check(result, operation):
        if result < 0:
            raise RuntimeError(f"RTL-SDR {operation} failed ({result}). Check USB connection.")

    def tune(self, frequency):
        self._check(self.lib.rtlsdr_set_center_freq(self.handle, frequency), "frequency change")
        self._check(self.lib.rtlsdr_reset_buffer(self.handle), "buffer reset")

    def read(self):
        count = ct.c_int()
        self._check(
            self.lib.rtlsdr_read_sync(self.handle, self.buffer, len(self.buffer), ct.byref(count)),
            "sample read",
        )
        if count.value != len(self.buffer):
            raise RuntimeError(f"Short USB read: {count.value}/{len(self.buffer)} bytes.")
        raw = np.ctypeslib.as_array(self.buffer).astype(np.float32)
        raw = (raw - 127.5) / 128.0
        return raw[::2] + 1j * raw[1::2]

    def close(self):
        if self.handle:
            self.lib.rtlsdr_close(self.handle)
            self.handle = ct.c_void_p()


class DemoSource:
    """Synthetic FM tone plus noise, not speech or an RF reception."""

    def __init__(self, device=0):
        self.rng = np.random.default_rng(42)
        self.index = 0
        self.phase = 0.0
        self.tone = 440
        self.deadline = time.monotonic()

    def tune(self, frequency):
        self.tone = 330 + (frequency // 100_000 % 12) * 55

    def read(self):
        self.deadline += BLOCK_SAMPLES / IQ_RATE
        time.sleep(max(0, self.deadline - time.monotonic()))
        # Avoid catching up indefinitely after a slow consumer.
        self.deadline = max(self.deadline, time.monotonic() - 0.05)
        t = (np.arange(BLOCK_SAMPLES) + self.index) / IQ_RATE
        modulation = 0.3 * np.sin(2 * np.pi * self.tone * t)
        phase = self.phase + np.cumsum(modulation * (2 * np.pi * 75_000 / IQ_RATE))
        self.phase = phase[-1] % (2 * np.pi)
        self.index += BLOCK_SAMPLES
        noise = self.rng.normal(0, 0.015, (2, BLOCK_SAMPLES))
        return (np.exp(1j * phase) + noise[0] + 1j * noise[1]).astype(np.complex64)

    def close(self):
        pass
