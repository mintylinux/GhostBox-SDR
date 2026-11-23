# GhostBox-SDR

**A Ghost Box–style RTL-SDR frequency sweeper for Linux, with desktop and
headless operation.**

Sweep through FM broadcast channels, listen to short radio snippets, and adjust
audio filtering to reduce rumble and hiss. Use the desktop interface on a Linux
computer or run from the command line on a headless system.

> **Early release · FM only.** Linux operation has been tested with an RTL-SDR
> Blog V4 on CachyOS. Raspberry Pi is an intended target, but performance and
> installation have not yet been verified on Pi hardware.

## Features

- **Three sweep modes:** forward, reverse, and random channel order.
- **Configurable scanning:** start/end frequency, channel spacing, dwell time,
  and settling time within a 64–108 MHz tuning range.
- **Audio cleanup:** optional 300–3400 Hz speech-band filter and an adjustable
  noise gate.
- **Playback controls:** volume adjustment, peak limiting, and short fades to
  reduce channel-switching clicks.
- **FM reception:** mono wideband FM with selectable 50 or 75 µs de-emphasis.
- **Desktop interface:** live frequency and uncalibrated input-level display.
- **Headless CLI:** no graphical desktop or Qt dependency required.
- **Demo mode:** synthetic FM tones for testing without a dongle.

The receiver keeps one connection to the SDR open while sweeping. Audio processing
runs locally; no cloud service, AI voice generation, or transcription is used.

## Hardware and requirements

- Linux and **Python 3.11 or newer**.
- An RTL-SDR USB receiver supported by your installed `librtlsdr`.
- An antenna suitable for FM broadcast reception.
- Working audio output through PortAudio/ALSA, PipeWire, or PulseAudio.
- For the GUI: PySide6 and a graphical desktop session.

**Tested receiver:** RTL-SDR Blog V4 with a V4-compatible system driver.
Other librtlsdr-compatible receivers may work but have not yet been verified.

For Raspberry Pi, a **Pi 4 or Pi 5 running 64-bit Raspberry Pi OS Bookworm or
newer** is the recommended starting point. Use a reliable power supply and a
supported audio output such as USB or HDMI. A powered USB hub may help if the
receiver draws more power than your setup can reliably supply.

## Installation

### 1. Install system dependencies

**CachyOS / Arch Linux**

```sh
sudo pacman -S --needed git python python-pip rtl-sdr portaudio
```

**Raspberry Pi OS / Debian / Ubuntu**

```sh
sudo apt update
sudo apt install git python3-venv python3-dev rtl-sdr librtlsdr0 libportaudio2
```

Package versions vary by distribution. **Blog V4 users need a V4-compatible
librtlsdr build**; installing the Python app does not upgrade your SDR driver.

### 2. Clone the project

```sh
git clone https://github.com/mintylinux/GhostBox-SDR.git
cd GhostBox-SDR
```

### 3. Create a virtual environment

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

### 4. Install the app

**Desktop version:**

```sh
.venv/bin/python -m pip install -e '.[gui]'
```

**Headless version, including Raspberry Pi without a desktop:**

```sh
.venv/bin/python -m pip install -e .
```

PySide6 wheel availability depends on Python version and architecture. Use a
64-bit OS on Raspberry Pi; if a compatible Qt wheel is unavailable, use headless
mode instead.

All examples use the virtual environment directly, so shell activation is
optional. They also work from fish.

#### Alternative: uv

If you already use [uv](https://docs.astral.sh/uv/), steps 3–4 can be replaced with:

```sh
uv venv .venv
uv pip install --python .venv/bin/python -e '.[gui]'
```

Omit `[gui]` for a headless installation.

## Quick start

1. Connect the RTL-SDR and antenna.
2. Close other programs that may be using the receiver.
3. Turn your speaker or headphone volume down.
4. Open the desktop app:

```sh
.venv/bin/ghostbox-sdr
```

5. Choose your frequency range and sweep settings, then click **Start sweep**.
6. Click **Stop** before changing settings.

The GUI does not begin receiving or playing audio until you start a sweep.
Settings are locked while running; stop and restart to apply changes.

### Try it without hardware

```sh
.venv/bin/ghostbox-sdr --demo
```

Demo mode produces **synthetic tones and noise**, not voices or received stations.
The app does not access the SDR in this mode.

## Headless usage

Run the default sweep:

```sh
.venv/bin/ghostbox-sdr --headless
```

The defaults are **88.1–107.9 MHz**, **200 kHz** spacing, **150 ms** of audio per
channel, **40 ms** settling time, and forward scanning.

### Random or reverse scanning

```sh
.venv/bin/ghostbox-sdr --headless --direction random --volume 0.2
.venv/bin/ghostbox-sdr --headless --direction reverse
```

Random mode shuffles the frequency list once per sweep, visiting each channel
before reshuffling.

### Choose a frequency range and speed

```sh
.venv/bin/ghostbox-sdr --headless --start 90.1 --end 100.1 --step 200 --dwell 100
```

Frequency limits are in **MHz**, spacing is in **kHz**, and dwell/settling times
are in **milliseconds**.

For a 100 kHz channel grid with 50 µs de-emphasis:

```sh
.venv/bin/ghostbox-sdr --headless --start 87.5 --end 108 --step 100 --deemphasis 50
```

The default grid and 75 µs de-emphasis suit North America. Adjust these settings
for your local broadcast standard.

### Adjust audio cleanup

```sh
.venv/bin/ghostbox-sdr --headless --gate -45 --volume 0.2
.venv/bin/ghostbox-sdr --headless --wide-audio
```

- The **speech filter** keeps approximately 300–3400 Hz to reduce low-frequency
  rumble and high-frequency hiss. `--wide-audio` disables it.
- The **noise gate** mutes audio below a threshold in dBFS. Moving the threshold
  closer to zero makes it more aggressive; `-100` makes it very permissive.
- The gate operates on **audio level**, not station strength. Loud static can
  still pass. It is not RF squelch or spectral denoising.
- The **volume control** ranges from `0` to `1`; the default is `0.4`.
- **Peak limiting** constrains digital peaks but does not guarantee a safe
  listening volume. Start low.

### Check a known local station

Set both frequency limits to the same value and use a longer dwell:

```sh
.venv/bin/ghostbox-sdr --headless --start 99.5 --end 99.5 --dwell 10000 --wide-audio
```

Replace `99.5` with a station in your area. This is useful for checking your
antenna and audio output. The current implementation still briefly retunes
between dwell periods, even when only one frequency is selected.

### Select devices

```sh
.venv/bin/ghostbox-sdr --list-devices
.venv/bin/ghostbox-sdr --list-audio
```

Use the reported indices to select a receiver or output. For example, if the
desired SDR is index `0` and the audio output is index `3`:

```sh
.venv/bin/ghostbox-sdr --headless --device 0 --audio-device 3
```

Device indices may change after reconnecting hardware. `--audio-device` also
works when launching the GUI.

### Timed and silent runs

Process real RF samples for five seconds without opening audio output:

```sh
.venv/bin/ghostbox-sdr --headless --silent --duration 5
```

Test the pipeline without SDR hardware or playback:

```sh
.venv/bin/ghostbox-sdr --headless --demo --silent --duration 3
```

**`--silent` disables playback, not reception. `--demo` disables hardware access.**
`--duration` requires `--headless`. Press **Ctrl+C** to stop an untimed CLI run.

For the complete option list:

```sh
.venv/bin/ghostbox-sdr --help
```

## How it works

The signal path is:

**RTL-SDR IQ samples → channel filtering → FM demodulation → de-emphasis →
audio filtering → noise gate → volume/peak limiting → audio output**

- Input sample rate: **1.2 MS/s**.
- Output: **48 kHz mono** audio.
- Sample block duration: **20.48 ms**.
- Dwell and settling times round up to whole sample blocks.
- Each hop also incurs tuner and USB overhead.

The dwell setting is the amount of retained audio per channel, **not the total
time between frequency changes**. Samples captured during settling are discarded,
so short gaps between snippets are expected. Fades reduce clicks but do not make
switching seamless.

The input-level display is an uncalibrated digital sample level, **not dBm** or a
calibrated RF signal-strength measurement.

## Current limitations

- **FM only:** AM and shortwave reception are not implemented.
- No audio recording, session export, or frequency/timestamp logs yet.
- No spectral denoising, AI enhancement, or speech recognition.
- No Android, iOS, or web interface.
- No stereo decoding or RDS.
- No live changes to scan/audio settings while sweeping.
- Raspberry Pi operation and performance still need hardware testing.

Short snippets can clip words, and aggressive filtering can distort or remove
speech. Cleanup cannot reconstruct audio that was never captured.

## Troubleshooting

### No RTL-SDR found

Check the connection with `lsusb` and run `--list-devices`. Try another USB port,
data cable, or powered hub. A receiver may disconnect if USB power is unreliable.

### Cannot open the receiver

Close SDR++, GQRX, `rtl_tcp`, or other programs that may own the dongle.
Check your distribution's RTL-SDR udev rules and guidance for conflicts with
the Linux DVB driver. Reconnect the dongle after installing device rules.
**Do not run the desktop app as root.**

### Blog V4 is detected but reception is wrong

Confirm that the installed system `librtlsdr` supports Blog V4. This app loads
that library directly; it cannot add V4 support to an older driver.

### No sound or the wrong output

Run `--list-audio`, select an output with `--audio-device`, and check your
PipeWire/PulseAudio/ALSA mixer. Make sure **Silent** is not enabled and the volume
is above zero. Use `--demo` to test playback independently of radio reception.
If the gate is suppressing everything, try `--gate -100`.

### Mostly static

Attach an FM-suitable antenna, try a known strong station with a long dwell,
and verify your region's channel spacing. Increase settling time if the
beginning of each snippet is unstable. A noise gate will not eliminate loud hiss.

### Glitches on Raspberry Pi

Start with headless mode, use reliable USB power, and reduce other CPU-heavy
work. The Python DSP pipeline has not yet been benchmarked on Pi hardware.

### Slow shutdown after a USB fault

Stop/Ctrl+C requests cooperative shutdown after the current synchronous USB read.
A stalled USB read or broken driver can delay shutdown.

## Development

Install the development tools, with GUI dependencies for desktop tests:

```sh
.venv/bin/python -m pip install -e '.[gui,dev]'
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Tests cover frequency ordering and validation, synthetic FM demodulation, filter
state across sample blocks, speech filtering, audio buffering, resource cleanup,
CLI behavior, and offscreen GUI start/stop. GUI tests are skipped when PySide6
is not installed. Automated tests do not require an SDR or audio device.

Bug reports and contributions are welcome through
[GitHub Issues](https://github.com/mintylinux/GhostBox-SDR/issues) and pull requests.
For reception problems, include your OS, Python version, dongle model, driver
version, settings, and relevant error output.

## Responsible use

GhostBox-SDR is an experimental radio-scanning and audio-effects tool. Broadcast
fragments, interference, and perceived patterns in noise are not scientifically
validated evidence of paranormal communication.

The application is receive-only. It does not transmit, enable the bias tee,
unload kernel modules, or change system configuration. Follow local radio
reception laws and keep playback at a comfortable volume.

## License

[MIT License](LICENSE) — Copyright © 2026 mintylinux.
