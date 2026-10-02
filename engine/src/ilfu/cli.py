"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .capture import Recorder, get_backend
from .evaluation import compare, evaluate, load_manifest
from .hardware import choose_tier, detect_hardware
from .models import MODELS
from .transcript import FORMATS
from .uninstall import launch_uninstaller


def _cmd_setup(args: argparse.Namespace) -> int:
    """Headless version of the first-run setup window (also used by CI)."""
    from . import config, models

    if not args.accept_terms:
        print("Read the agreement in the setup window or docs, then pass --accept-terms.")
        return 2
    hw = detect_hardware()
    name = args.model or models.recommended(hw.cpu_cores, hw.ram_gb, hw.has_cuda)
    print(f"Downloading model '{name}' ({models.info(name).size_mb} MB)...")
    models.download(name, lambda f: print(f"\r{f:.0%}", end="", flush=True))
    print()
    cfg = config.load()
    cfg.model, cfg.language = name, args.language
    cfg.save_dir = str(args.save_dir) if args.save_dir else cfg.save_dir
    cfg.terms_version, cfg.setup_done = config.TERMS_VERSION, True
    config.save(cfg)
    print(f"Setup saved to {config.config_path()}")
    return 0


def _cmd_benchmark(args: argparse.Namespace) -> int:
    from . import benchmark

    items = []
    for tag in args.languages.split(","):
        print(f"Preparing {tag} clips...", flush=True)
        items += benchmark.download(tag, args.cache, benchmark.FROZEN_COUNT)
    current, problems = benchmark.freeze_check(items, args.frozen)
    if problems:
        print("The test audio is not the frozen set:\n  " + "\n  ".join(problems))
        return 3
    if not args.frozen.exists():
        args.frozen.parent.mkdir(parents=True, exist_ok=True)
        args.frozen.write_text(json.dumps(current, indent=1, sort_keys=True), encoding="utf-8")
        print(f"No frozen list yet: wrote {args.frozen}. Commit it so the set stays fixed.")
        print("FROZEN-LIST-BEGIN\n" + args.frozen.read_text(encoding="utf-8") + "\nFROZEN-LIST-END")
    if args.count < benchmark.FROZEN_COUNT:  # a quick run uses the first clips of the frozen set
        seen: dict[str, int] = {}
        quick = []
        for item in items:
            seen[item.tag] = seen.get(item.tag, 0) + 1
            if seen[item.tag] <= args.count:
                quick.append(item)
        items = quick
    from .transcribe import FasterWhisperTranscriber

    tier = choose_tier(detect_hardware())
    transcriber = FasterWhisperTranscriber(
        tier, model=args.model, beam_size=args.beam_size, cpu_threads=args.threads
    )
    report = benchmark.run(items, transcriber, args.label or args.model)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown = benchmark.to_markdown(report)
    print(markdown)
    for tag, rows in report.get("samples", {}).items():
        for row in rows:
            print(f"[{tag}] reference: {row['reference']}\n[{tag}] heard:     {row['heard']}")
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(markdown)
    return 0


def _cmd_devices(args: argparse.Namespace) -> int:
    backend = get_backend(args.backend)
    for name in backend.list_devices():
        print(name)
    print("Microphones you can choose:", ", ".join(backend.list_microphones()) or "(default only)")
    print("Outputs you can capture:", ", ".join(backend.list_speakers()) or "(default only)")
    backend.close()
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


def _cmd_gui(args: argparse.Namespace) -> int:
    from .gui import main as gui_main

    return gui_main(args.backend, show_window=not args.no_window)


def _cmd_uninstall(args: argparse.Namespace) -> int:
    print(launch_uninstaller())
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

    su = sub.add_parser("setup", help="download a speech model and save settings, no window")
    su.add_argument("--model", choices=[m.name for m in MODELS])
    su.add_argument("--language", default="auto")
    su.add_argument("--save-dir", type=Path)
    su.add_argument("--accept-terms", action="store_true")
    su.set_defaults(run=_cmd_setup)

    gui = sub.add_parser("gui", help="open the app window")
    gui.add_argument("--no-window", action="store_true", help="only print the address")
    gui.set_defaults(run=_cmd_gui)
    sub.add_parser("uninstall", help="remove the app (Windows installer)").set_defaults(
        run=_cmd_uninstall
    )

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

    bm = sub.add_parser("benchmark", help="measure accuracy and speed on the frozen FLEURS clips")
    bm.add_argument("--model", required=True, choices=[m.name for m in MODELS])
    bm.add_argument("--languages", default="en,hi,te")
    bm.add_argument(
        "--count", type=int, default=25, help="clips per language to transcribe (frozen set: 25)"
    )
    bm.add_argument("--cache", type=Path, default=Path("benchmark-cache"))
    bm.add_argument("--frozen", type=Path, default=Path("benchmark/frozen-clips.json"))
    bm.add_argument("--out", type=Path, default=Path("benchmark-report.json"))
    bm.add_argument("--summary", type=Path, help="append a Markdown table to this file")
    bm.add_argument("--label", help="name for this run in the report")
    bm.add_argument("--beam-size", type=int, default=5)
    bm.add_argument("--threads", type=int, help="CPU threads (default: about half the cores)")
    bm.set_defaults(run=_cmd_benchmark)

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
