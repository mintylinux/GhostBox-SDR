import argparse
import math
import signal
import sys

from .engine import SweepConfig, SweepEngine
from .radio import devices


def parser():
    result = argparse.ArgumentParser(description="Receive-only RTL-SDR FM sweeping tool")
    result.add_argument("--headless", action="store_true", help="Run without the desktop UI")
    result.add_argument("--demo", action="store_true", help="Synthetic tones, not radio reception")
    result.add_argument(
        "--silent", action="store_true", help="Process without opening audio output"
    )
    result.add_argument("--list-devices", action="store_true", help="List RTL-SDR devices")
    result.add_argument("--list-audio", action="store_true", help="List PortAudio devices")
    result.add_argument("--start", type=float, default=88.1, help="Start frequency, MHz")
    result.add_argument("--end", type=float, default=107.9, help="End frequency, MHz")
    result.add_argument("--step", type=float, default=200, help="Channel spacing, kHz")
    result.add_argument(
        "--dwell", type=int, default=150, help="Audio dwell, ms (excludes settling)"
    )
    result.add_argument("--settle", type=int, default=40, help="Discard after each retune, ms")
    result.add_argument("--direction", choices=["forward", "reverse", "random"], default="forward")
    result.add_argument("--volume", type=float, default=0.4, help="Volume, 0–1")
    result.add_argument("--gate", type=float, default=-55, help="Audio gate threshold, dBFS")
    result.add_argument(
        "--wide-audio", action="store_true", help="Disable 300–3400 Hz speech filter"
    )
    result.add_argument(
        "--deemphasis", type=int, choices=[50, 75], default=75, help="FM de-emphasis, µs"
    )
    result.add_argument("--device", type=int, default=0, help="RTL-SDR device index")
    result.add_argument("--audio-device", type=int, help="PortAudio output device index")
    result.add_argument(
        "--duration", type=float, help="Stop headless reception after this many seconds"
    )
    return result


def main(argv=None):
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        if args.list_devices:
            found = devices()
            for index, name in found:
                print(f"{index}: {name}")
            if not found:
                print("No RTL-SDR devices found.")
            return 0
        if args.list_audio:
            import sounddevice as sd

            print(sd.query_devices())
            return 0
        if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
            arguments.error("--duration must be a finite positive number")
        if args.duration is not None and not args.headless:
            arguments.error("--duration requires --headless")
        config = SweepConfig(
            start_mhz=args.start,
            stop_mhz=args.end,
            step_khz=args.step,
            dwell_ms=args.dwell,
            settle_ms=args.settle,
            direction=args.direction,
            speech=not args.wide_audio,
            volume=args.volume,
            gate_db=args.gate,
            deemphasis_us=args.deemphasis,
            device=args.device,
            demo=args.demo,
            silent=args.silent,
            audio_device=args.audio_device,
        )
        if not args.headless:
            from .gui import launch

            return launch(config)

        last_frequency = None

        def status(update):
            nonlocal last_frequency
            if update["frequency"] != last_frequency:
                last_frequency = update["frequency"]
                prefix = "DEMO · synthetic tone" if config.demo else "FM"
                print(f"{prefix}: {last_frequency / 1e6:.3f} MHz", flush=True)

        engine = SweepEngine(config, on_status=status)
        old_handlers = {
            sig: signal.signal(sig, lambda *_: engine.stop())
            for sig in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            engine.run(duration=args.duration)
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
        return 0
    except ImportError as error:
        print(
            f"Missing dependency: {error}. For desktop support install '.[gui]'.", file=sys.stderr
        )
        return 1
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
