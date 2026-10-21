"""Generate a text-only synthetic OCR test image, never a portal CAPTCHA capture."""
from __future__ import annotations

import argparse
from pathlib import Path


def main():
    from PIL import Image, ImageDraw, ImageFont
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', default='C:/Windows/Fonts/arialbd.ttf')
    parser.add_argument('--output', type=Path, default=Path('tests/fixtures/sample_captcha.png'))
    args = parser.parse_args()
    image = Image.new('RGB', (150, 38), 'white')
    ImageDraw.Draw(image).text((18, 0), 'abc12', font=ImageFont.truetype(args.font, 28), fill=(30, 40, 50))
    image.save(args.output)


if __name__ == '__main__':
    main()
