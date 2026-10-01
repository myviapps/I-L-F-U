"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .capture import Recorder, get_backend
from .evaluation import compare, evaluate, load_manifest
from .hardware import choose_tier, detect_hardware
from .transcript import FORMATS


def _cmd_devices(args: argparse.Namespace) -> int:
    for name in get_backend(args.backend).list_devices():
        print(name)
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    backend = get_backend(args.backend)
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


def _cmd_tier(args: argparse.Namespace) -> int:
    hw = detect_hardware()
    tier = choose_tier(hw)
    print(f"Machine: {hw.cpu_cores} cores, {hw.ram_gb} GB RAM, CUDA GPU: {hw.has_cuda}")
    print(f"Tier: {tier.name} (model {tier.model}, {tier.compute_type} on {tier.device})")
    print(f"Live captions: {'yes' if tier.live_captions else 'no, transcribe after the call'}")
    return 0


def _cmd_transcribe(args: argparse.Namespace) -> int:
    from .transcribe import FasterWhisperTranscriber

    tier = choose_tier(detect_hardware())
    if args.model:
        tier = type(tier)(tier.name, args.model, tier.compute_type, tier.device, tier.live_captions)
    segments = FasterWhisperTranscriber(tier, args.language).transcribe(args.audio)
    output = FORMATS[args.format](segments)
    if args.out:
        args.out.write_text(output, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(output, end="")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from .transcribe import FasterWhisperTranscriber

    tier = choose_tier(detect_hardware())
    transcriber = FasterWhisperTranscriber(tier)
    report = evaluate(load_manifest(args.manifest), transcriber, label=tier.model)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"WER {report['wer']:.3f} on {report['clips']} clips, saved to {args.out}")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    old = json.loads(args.old.read_text(encoding="utf-8"))
    new = json.loads(args.new.read_text(encoding="utf-8"))
    ok, lines = compare(old, new, args.max_regression)
    print("\n".join(lines))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ilfu", description="Open-source call transcriber")
    parser.add_argument("--backend", default="auto", help="capture backend: auto, windows, fake")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="list audio devices").set_defaults(run=_cmd_devices)

    rec = sub.add_parser("record", help="record system audio and microphone to WAV files")
    rec.add_argument("--seconds", type=float, default=10.0)
    rec.add_argument("--out", type=Path, default=Path("recording"))
    rec.set_defaults(run=_cmd_record)

    sub.add_parser("tier", help="show this machine and the model tier chosen for it").set_defaults(
        run=_cmd_tier
    )

    tr = sub.add_parser("transcribe", help="transcribe an audio file locally")
    tr.add_argument("audio", type=Path)
    tr.add_argument("--format", choices=sorted(FORMATS), default="txt")
    tr.add_argument("--model", help="override the automatic model choice, e.g. tiny or small")
    tr.add_argument("--language", help="language code such as en; auto-detected if omitted")
    tr.add_argument("--out", type=Path)
    tr.set_defaults(run=_cmd_transcribe)

    ev = sub.add_parser("eval", help="run the benchmark and save a WER report")
    ev.add_argument("manifest", type=Path, help="JSON-lines manifest of audio and reference text")
    ev.add_argument("--out", type=Path, default=Path("report.json"))
    ev.set_defaults(run=_cmd_eval)

    cmp_ = sub.add_parser("compare", help="compare two reports; exit 1 on regression")
    cmp_.add_argument("old", type=Path)
    cmp_.add_argument("new", type=Path)
    cmp_.add_argument("--max-regression", type=float, default=0.005)
    cmp_.set_defaults(run=_cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
