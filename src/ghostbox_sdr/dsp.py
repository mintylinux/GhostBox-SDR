"""Stateful mono wideband-FM demodulation, de-emphasis, and audio filtering."""

import numpy as np
from scipy import signal

from .radio import IQ_RATE

AUDIO_RATE = 48_000
CHANNEL_RATE = IQ_RATE // 5


class FmProcessor:
    def __init__(self, speech=True, gate_db=-55.0, volume=0.4, deemphasis_us=75):
        self.speech = speech
        self.gate_db = gate_db
        self.volume = volume
        self.rf_taps = signal.firwin(121, 100_000, fs=IQ_RATE)
        self.audio_taps = signal.firwin(101, 15_000, fs=CHANNEL_RATE)
        self.speech_sos = signal.butter(
            4, [300, 3_400], btype="bandpass", fs=AUDIO_RATE, output="sos"
        )
        pole = np.exp(-1 / (CHANNEL_RATE * deemphasis_us * 1e-6))
        self.de_b = [1 - pole]
        self.de_a = [1, -pole]
        self.reset()

    def reset(self):
        self.rf_state = np.zeros(len(self.rf_taps) - 1, dtype=np.complex128)
        self.audio_state = np.zeros(len(self.audio_taps) - 1)
        self.de_state = np.zeros(1)
        self.speech_state = np.zeros((len(self.speech_sos), 2))
        self.previous = 1 + 0j
        self.rf_offset = 0
        self.audio_offset = 0
        self.fade_remaining = int(AUDIO_RATE * 0.005)
        self.gate_gain = 0.0

    def process(self, iq):
        rf, self.rf_state = signal.lfilter(self.rf_taps, [1], iq, zi=self.rf_state)
        channel = rf[self.rf_offset :: 5]
        self.rf_offset = (self.rf_offset - len(rf)) % 5
        if not len(channel):
            return np.empty(0, dtype=np.float32)
        prior = np.concatenate(([self.previous], channel[:-1]))
        self.previous = channel[-1]
        demod = np.angle(channel * np.conjugate(prior)) * (CHANNEL_RATE / (2 * np.pi * 75_000))
        audio, self.de_state = signal.lfilter(self.de_b, self.de_a, demod, zi=self.de_state)
        audio, self.audio_state = signal.lfilter(self.audio_taps, [1], audio, zi=self.audio_state)
        audio = audio[self.audio_offset :: 5]
        self.audio_offset = (self.audio_offset - len(channel)) % 5
        if self.speech:
            audio, self.speech_state = signal.sosfilt(self.speech_sos, audio, zi=self.speech_state)
        if not len(audio):
            return np.empty(0, dtype=np.float32)
        rms = np.sqrt(np.mean(audio**2) + 1e-20)
        target = float(20 * np.log10(rms) >= self.gate_db)
        gains = np.linspace(self.gate_gain, target, len(audio))
        self.gate_gain = target
        audio *= gains * self.volume
        if self.fade_remaining:
            total = int(AUDIO_RATE * 0.005)
            count = min(self.fade_remaining, len(audio))
            start = total - self.fade_remaining
            audio[:count] *= np.arange(start, start + count) / total
            self.fade_remaining -= count
        return np.clip(audio, -0.95, 0.95).astype(np.float32)
