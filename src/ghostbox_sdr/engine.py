"""Sweep configuration and a shared engine for desktop and headless operation."""

import math
import queue
import random
import threading
import time
from dataclasses import dataclass

import numpy as np

from .dsp import AUDIO_RATE, FmProcessor
from .radio import BLOCK_SAMPLES, IQ_RATE, DemoSource, RtlSource


@dataclass(frozen=True)
class SweepConfig:
    start_mhz: float = 88.1
    stop_mhz: float = 107.9
    step_khz: float = 200
    dwell_ms: int = 150
    settle_ms: int = 40
    direction: str = "forward"
    speech: bool = True
    gate_db: float = -55
    volume: float = 0.4
    deemphasis_us: int = 75
    device: int = 0
    demo: bool = False
    silent: bool = False
    audio_device: int | None = None

    def __post_init__(self):
        numbers = (self.start_mhz, self.stop_mhz, self.step_khz, self.gate_db, self.volume)
        if not all(math.isfinite(x) for x in numbers):
            raise ValueError("Settings must be finite numbers.")
        if not 64 <= self.start_mhz <= self.stop_mhz <= 108:
            raise ValueError("FM range must be ordered and within 64–108 MHz.")
        if not 25 <= self.step_khz <= 2_000:
            raise ValueError("Frequency spacing must be 25–2000 kHz.")
        if not 40 <= self.dwell_ms <= 10_000:
            raise ValueError("Dwell must be 40–10000 ms.")
        if not 0 <= self.settle_ms <= 500:
            raise ValueError("Settling time must be 0–500 ms.")
        if self.direction not in ("forward", "reverse", "random"):
            raise ValueError("Unknown scan direction.")
        if not 0 <= self.volume <= 1 or not -100 <= self.gate_db <= 0:
            raise ValueError("Volume must be 0–1 and gate must be -100–0 dBFS.")
        if self.deemphasis_us not in (50, 75):
            raise ValueError("De-emphasis must be 50 or 75 microseconds.")
        if self.device < 0:
            raise ValueError("Device index cannot be negative.")

    def frequencies(self):
        start = round(self.start_mhz * 1e6)
        stop = round(self.stop_mhz * 1e6)
        step = round(self.step_khz * 1e3)
        return list(range(start, stop + 1, step))


def frequency_order(config, rng=None):
    rng = rng or random.Random()
    frequencies = config.frequencies()
    while True:
        order = frequencies.copy()
        if config.direction == "reverse":
            order.reverse()
        elif config.direction == "random":
            rng.shuffle(order)
        yield from order


class AudioOutput:
    def __init__(self, device=None):
        import sounddevice as sd

        self.blocks = queue.Queue(maxsize=12)
        self.pending = np.empty(0, dtype=np.float32)
        self.stream = sd.OutputStream(
            samplerate=AUDIO_RATE,
            channels=1,
            dtype="float32",
            blocksize=960,
            device=device,
            callback=self._callback,
        )

    def _callback(self, outdata, frames, timing, status):
        outdata.fill(0)
        position = 0
        while position < frames:
            if not len(self.pending):
                try:
                    self.pending = self.blocks.get_nowait()
                except queue.Empty:
                    break
            count = min(frames - position, len(self.pending))
            outdata[position : position + count, 0] = self.pending[:count]
            self.pending = self.pending[count:]
            position += count

    def write(self, audio):
        try:
            self.blocks.put_nowait(audio)
        except queue.Full:
            # Bound latency: discard the oldest queued audio, not the newest.
            try:
                self.blocks.get_nowait()
            except queue.Empty:
                pass
            self.blocks.put_nowait(audio)

    def start(self):
        self.stream.start()

    def close(self):
        self.stream.stop()
        self.stream.close()


class SweepEngine:
    def __init__(self, config, on_status=None, source_factory=None, output_factory=None):
        self.config = config
        self.on_status = on_status or (lambda status: None)
        self.stop_event = threading.Event()
        self.source_factory = source_factory or (DemoSource if config.demo else RtlSource)
        self.output_factory = output_factory or AudioOutput

    def stop(self):
        self.stop_event.set()

    def run(self, duration=None):
        config = self.config
        processor = FmProcessor(config.speech, config.gate_db, config.volume, config.deemphasis_us)
        source = None
        output = None
        deadline = math.inf if duration is None else time.monotonic() + duration
        # Sample-based dwell avoids DSP speed changing the amount of radio audio captured.
        dwell_blocks = math.ceil(config.dwell_ms / 1000 * IQ_RATE / BLOCK_SAMPLES)
        settle_blocks = math.ceil(config.settle_ms / 1000 * IQ_RATE / BLOCK_SAMPLES)

        def stopped():
            return self.stop_event.is_set() or time.monotonic() >= deadline

        try:
            if not config.silent:
                output = self.output_factory(config.audio_device)
                output.start()
            source = self.source_factory(config.device)
            for frequency in frequency_order(config):
                if stopped():
                    break
                source.tune(frequency)
                processor.reset()
                self.on_status(
                    {
                        "frequency": frequency,
                        "demo": config.demo,
                        "level_db": None,
                    }
                )
                # Capture/discard while the tuner settles; no stale samples are played.
                for _ in range(settle_blocks):
                    if stopped():
                        break
                    source.read()
                for index in range(dwell_blocks):
                    if stopped():
                        break
                    iq = source.read()
                    audio = processor.process(iq)
                    if index == dwell_blocks - 1:
                        count = min(len(audio), int(AUDIO_RATE * 0.005))
                        if count:
                            audio[-count:] *= np.linspace(1, 0, count)
                    if output is not None:
                        output.write(audio)
                    level = float(10 * np.log10(np.mean(np.abs(iq) ** 2) + 1e-20))
                    self.on_status(
                        {
                            "frequency": frequency,
                            "demo": config.demo,
                            "level_db": level,
                        }
                    )
        finally:
            try:
                if source is not None:
                    source.close()
            finally:
                if output is not None:
                    output.close()
