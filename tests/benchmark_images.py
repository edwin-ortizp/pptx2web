"""Compare 1/2 image workers without COM. python tests/benchmark_images.py --out <folder>.
Synthetic 20-slide workload when the original presentation is unavailable.
"""
import argparse
import json
from pathlib import Path
import random
import shutil
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PIL import Image, ImageDraw
from pptx2web import images
from pptx2web.models import RenderedSlide


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sources = args.out / 'sources'
    sources.mkdir(exist_ok=True)
    rng = random.Random(20261009)
    for index in range(1, 21):
        im = Image.new('RGB', (1280, 720), (240, 240, 245))
        draw = ImageDraw.Draw(im)
        draw.text((50, 40), f'Slide {index}', fill=(20, 30, 70))
        for y in range(120, 620, 45):
            draw.rectangle((50, y, 700 + index * 10, y + 12), fill=(index * 10, 60, 120))
        if index == 17:
            noise = Image.frombytes('RGB', (800, 500), rng.randbytes(800 * 500 * 3))
            im.paste(noise, (300, 150))
            noise.close()
        im.save(sources / f'{index}.png')
        im.close()
    timings = {1: [], 2: []}
    reference = None
    equivalent = True
    # Interleave modes to reduce warm-up and scheduling bias.
    for run in range(3):
        for workers in ((1, 2) if run % 2 == 0 else (2, 1)):
            folder = args.out / f'run-{run}-workers-{workers}'
            folder.mkdir()
            rendered = []
            for index in range(1, 21):
                path = folder / f'{index}.png'
                shutil.copyfile(sources / f'{index}.png', path)
                rendered.append(RenderedSlide(index=index, png_path=path, width_px=1280, height_px=720))
            start = time.monotonic()
            assets, warnings = images._process_images(rendered, folder, 82, 'avif', workers=workers)
            timings[workers].append(time.monotonic() - start)
            content = [(a.index, (folder / a.src).read_bytes(), (folder / a.thumb).read_bytes()) for a in assets]
            if reference is None:
                reference = content
            equivalent = equivalent and content == reference
            print(f'run={run} workers={workers} seconds={timings[workers][-1]:.3f}', flush=True)
    medians = {workers: statistics.median(values) for workers, values in timings.items()}
    result = {'workload': 'synthetic, 20 slides, 1280x720, AVIF quality=82 speed=6',
              'seconds': timings, 'medians_seconds': medians, 'byte_identical': equivalent,
              'improvement_percent': 100 * (1 - medians[2] / medians[1])}
    (args.out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
