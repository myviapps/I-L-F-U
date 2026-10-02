"""Run AI4Bharat IndicConformer on the frozen FLEURS Hindi and Telugu clips (MIT licence).

CI only. It loads the model code published with the model on Hugging Face (trust_remote_code),
so it is not part of the app. Prints word error rate, speed, memory and sample lines.
"""

import json
import resource
import sys
import time
from pathlib import Path

import torch
import torchaudio
from transformers import AutoModel

from ilfu import benchmark
from ilfu.evaluation import Item
from ilfu.wer import corpus_wer

MODEL = "ai4bharat/indic-conformer-600m-multilingual"
COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 25
DECODERS = ("ctc", "rnnt")

model = AutoModel.from_pretrained(MODEL, trust_remote_code=True)
items: dict[str, list[Item]] = {}
for tag in ("hi", "te"):
    items[tag] = benchmark.download(tag, Path("benchmark-cache"), benchmark.FROZEN_COUNT)[:COUNT]

report: dict = {"model": MODEL, "clips": COUNT}
for decoder in DECODERS:
    pairs_all, per_tag, work, audio = [], {}, 0.0, 0.0
    samples = []
    for tag, group in items.items():
        pairs = []
        for item in group:
            wav, rate = torchaudio.load(str(item.audio))
            wav = wav.mean(dim=0, keepdim=True)
            if rate != 16000:
                wav = torchaudio.functional.resample(wav, rate, 16000)
            started = time.perf_counter()
            with torch.no_grad():
                text = str(model(wav, tag, decoder))
            work += time.perf_counter() - started
            audio += wav.shape[1] / 16000
            pairs.append((item.reference, text))
            if len(samples) < 6 and sum(1 for s in samples if s[0] == tag) < 3:
                samples.append((tag, item.reference, text))
        per_tag[tag] = corpus_wer(pairs).wer
        pairs_all += pairs
    report[decoder] = {
        "wer_by_tag": per_tag,
        "wer": corpus_wer(pairs_all).wer,
        "real_time_factor": round(work / audio, 3),
    }
    print(f"\n### IndicConformer 600M multilingual, {decoder} decoding ({COUNT} clips per language)")
    for tag, value in per_tag.items():
        print(f"{'Hindi' if tag == 'hi' else 'Telugu'}: {value:.1%}")
    print(f"Speed: {report[decoder]['real_time_factor']} seconds of work per second of audio")
    for tag, ref, hyp in samples:
        print(f"[{tag}] reference: {ref}\n[{tag}] heard:     {hyp}")

report["peak_memory_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
print(f"Peak memory: {report['peak_memory_mb']} MB")
Path("report-indicconformer.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
