"""Command line entry point: `ilfu devices` and `ilfu record`."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from .capture import Recorder, get_backend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ilfu", description="Open-source call transcriber")
    parser.add_argument("--backend", default="auto", help="auto, windows or fake")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="list audio devices")
    rec = sub.add_parser("record", help="record system audio and microphone to WAV files")
    rec.add_argument("--seconds", type=float, default=10.0)
    rec.add_argument("--out", type=Path, default=Path("recording"))
    args = parser.parse_args(argv)

    backend = get_backend(args.backend)
    if args.command == "devices":
        for name in backend.list_devices():
            print(name)
        return 0

    recorder = Recorder(
        {"system": backend.open_system_audio(), "mic": backend.open_microphone()}, args.out
    )
    recorder.start()
    try:
        time.sleep(args.seconds)
    finally:
        dropped = recorder.stop()
    print(f"Saved to {args.out}. Dropped blocks: {dropped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
