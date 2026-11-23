import itertools
import queue
import random

import numpy as np
import pytest

from ghostbox_sdr.cli import main
from ghostbox_sdr.dsp import AUDIO_RATE, FmProcessor
from ghostbox_sdr.engine import AudioOutput, SweepConfig, SweepEngine, frequency_order
from ghostbox_sdr.radio import BLOCK_SAMPLES, IQ_RATE


@pytest.mark.parametrize(
    "settings",
    [
        {"start_mhz": 109},
        {"stop_mhz": 80},
        {"step_khz": 0},
        {"start_mhz": float("nan")},
        {"volume": float("inf")},
        {"dwell_ms": 0},
        {"settle_ms": -1},
        {"gate_db": 1},
        {"volume": 2},
        {"direction": "sideways"},
        {"device": -1},
        {"deemphasis_us": 100},
    ],
)
def test_invalid_settings(settings):
    with pytest.raises(ValueError):
        SweepConfig(**settings)


def test_frequency_grid_no_float_drift():
    frequencies = SweepConfig().frequencies()
    assert len(frequencies) == 100
    assert frequencies[0] == 88_100_000
    assert frequencies[-1] == 107_900_000
    assert set(np.diff(frequencies)) == {200_000}


@pytest.mark.parametrize("direction", ["forward", "reverse", "random"])
def test_sweep_order_repeats_without_missing_channels(direction):
    config = SweepConfig(start_mhz=90, stop_mhz=90.4, direction=direction)
    order = frequency_order(config, random.Random(3))
    first = list(itertools.islice(order, 3))
    second = list(itertools.islice(order, 3))
    assert sorted(first) == sorted(second) == config.frequencies()
    if direction == "forward":
        assert first == config.frequencies()
    elif direction == "reverse":
        assert first == config.frequencies()[::-1]


def fm_tone(frequency=1000, seconds=0.2):
    t = np.arange(round(IQ_RATE * seconds)) / IQ_RATE
    modulation = 0.4 * np.sin(2 * np.pi * frequency * t)
    phase = np.cumsum(modulation * (2 * np.pi * 75_000 / IQ_RATE))
    return np.exp(1j * phase).astype(np.complex64)


def process_chunks(processor, samples, block_size=BLOCK_SAMPLES):
    return np.concatenate(
        [
            processor.process(samples[start : start + block_size])
            for start in range(0, len(samples), block_size)
        ]
    )


def test_fm_demodulation_recovers_tone_and_sample_count():
    audio = process_chunks(FmProcessor(gate_db=-100, volume=1), fm_tone())
    assert len(audio) == round(AUDIO_RATE * 0.2)
    assert np.isfinite(audio).all()
    stable = audio[2400:]
    spectrum = np.abs(np.fft.rfft(stable))
    peak = np.fft.rfftfreq(len(stable), 1 / AUDIO_RATE)[np.argmax(spectrum)]
    assert peak == pytest.approx(1000, abs=10)
    assert np.sqrt(np.mean(stable**2)) > 0.1
    assert np.max(np.abs(audio)) <= 0.95


def test_chunking_preserves_filter_state_and_decimation_alignment():
    iq = fm_tone(seconds=0.15)
    first = FmProcessor(gate_db=-100)
    second = FmProcessor(gate_db=-100)
    first.gate_gain = second.gate_gain = 1.0
    whole = first.process(iq)
    chunked = process_chunks(second, iq, block_size=1024)
    assert len(whole) == len(chunked)
    np.testing.assert_allclose(whole[2400:], chunked[2400:], atol=1e-6)


def test_speech_filter_attenuates_high_frequency():
    iq = fm_tone(frequency=9000)
    wide = process_chunks(FmProcessor(speech=False, gate_db=-100), iq)[2400:]
    speech = process_chunks(FmProcessor(speech=True, gate_db=-100), iq)[2400:]
    assert np.mean(speech**2) < np.mean(wide**2) * 0.01


def test_zero_volume_and_gate():
    iq = fm_tone()
    assert not np.any(process_chunks(FmProcessor(volume=0), iq))
    assert not np.any(process_chunks(FmProcessor(gate_db=0), iq))


class FakeSource:
    def __init__(self, fail=False):
        self.closed = False
        self.frequencies = []
        self.fail = fail
        self.reads = 0

    def tune(self, frequency):
        self.frequencies.append(frequency)

    def read(self):
        self.reads += 1
        if self.fail:
            raise RuntimeError("USB disconnected")
        return np.ones(BLOCK_SAMPLES, dtype=np.complex64)

    def close(self):
        self.closed = True


def test_engine_stop_and_cleanup():
    source = FakeSource()
    events = []

    def status(update):
        events.append(update)
        if len(events) == 4:
            engine.stop()

    engine = SweepEngine(
        SweepConfig(silent=True, settle_ms=0),
        source_factory=lambda _: source,
        on_status=status,
    )
    engine.run()
    assert source.closed
    assert len(events) == 4
    assert source.reads == 3


def test_engine_failure_releases_source():
    source = FakeSource(fail=True)
    engine = SweepEngine(SweepConfig(silent=True), source_factory=lambda _: source)
    with pytest.raises(RuntimeError, match="USB disconnected"):
        engine.run()
    assert source.closed


def test_audio_output_cleanup_on_source_failure():
    class Output:
        closed = False

        def start(self):
            pass

        def close(self):
            self.closed = True

    output = Output()

    def fail(_):
        raise RuntimeError("Open failed")

    engine = SweepEngine(SweepConfig(), source_factory=fail, output_factory=lambda _: output)
    with pytest.raises(RuntimeError, match="Open failed"):
        engine.run()
    assert output.closed


def test_audio_queue_fills_silence_without_blocking():
    # Test callback without requiring an audio device.
    output = AudioOutput.__new__(AudioOutput)
    output.blocks = queue.Queue(maxsize=12)
    output.pending = np.empty(0, dtype=np.float32)
    output.write(np.ones(10, dtype=np.float32))
    result = np.empty((20, 1), dtype=np.float32)
    output._callback(result, 20, None, None)
    np.testing.assert_array_equal(result[:10], 1)
    np.testing.assert_array_equal(result[10:], 0)
    for value in range(15):
        output.write(np.full(10, value, dtype=np.float32))
    assert output.blocks.qsize() == 12
    assert output.blocks.get_nowait()[0] == 3


def test_cli_timed_silent_demo(capsys):
    assert main(["--headless", "--demo", "--silent", "--duration", "0.08"]) == 0
    assert "DEMO" in capsys.readouterr().out


def test_cli_invalid_range(capsys):
    assert main(["--headless", "--start", "108", "--end", "88"]) == 1
    assert "FM range" in capsys.readouterr().err


def test_cli_invalid_duration():
    with pytest.raises(SystemExit) as error:
        main(["--headless", "--duration", "nan"])
    assert error.value.code == 2
