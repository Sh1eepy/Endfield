"""Download the selected public Endfield design assets with bounded requests.

Run from the project root. Sources and hashes are recorded beside the assets.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'web/assets/official'
BASE = 'https://web.hycdn.cn/endfield/official-v4/_next/static/media/'
ASSETS = {
    'query-orbit.jpg': 'https://gmedia.playstation.com/is/image/SIEPDC/arknights-endfield-screenshot-01-zh-hans-cn-21jan26?fmt=jpeg&wid=1920',
    'talos-keyvisual.jpg': BASE + 'kv-obt-pc.1d54f26f.jpg',
    'laevatain-portrait.png': BASE + 'laevatain.d0ca2837.png',
    'chen-portrait.png': BASE + 'chen.2a091fd4.png',
    'ardelia-portrait.png': BASE + 'ardelia.36d836c7.png',
    'perlica-portrait.png': BASE + 'perlica.6710bc97.png',
    'endministrator-portrait.png': BASE + 'endministrator2.1ec20a16.png',
    'home-background.jpg': BASE + 'bg.9e174372.jpg',
    'divider.png': BASE + 'section_divider_icon_lore.6968c414.png',
    'texture.png': BASE + 'points-bg.f3b559e8.png',
    'wave.png': BASE + 'wave-bg.8955885a.png',
    'landscape.jpg': BASE + 'bg.269aa2f3.jpg',
}


def fetch(entry):
    name, url = entry
    target = DEST / name
    if not target.exists():
        started = time.monotonic()
        data = bytearray()
        with httpx.stream('GET', url, timeout=15, follow_redirects=False) as response:
            response.raise_for_status()
            if not response.headers.get('content-type', '').startswith('image/'):
                raise ValueError('Unexpected media type')
            for part in response.iter_bytes():
                data.extend(part)
                if len(data) > 20 * 1024 * 1024 or time.monotonic() - started > 30:
                    raise ValueError('Asset exceeded download budget')
        target.write_bytes(data)
    data = target.read_bytes()
    return {'file': name, 'source': url, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


if __name__ == '__main__':
    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(fetch, ASSETS.items()))
    (DEST / 'sources.json').write_text(json.dumps({'reference': 'https://endfield.hypergryph.com/',
        'note': 'Official game artwork; original rights remain with the rights holders.',
        'assets': records}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved', len(records), 'assets')
