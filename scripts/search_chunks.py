import os, re, glob, argparse

parser = argparse.ArgumentParser(description='在 webpack chunk 目录中搜索关键词/正则，结果落盘 UTF-8 文件')
parser.add_argument('--chunk-dir', default='chunks', help='chunk 目录，默认 ./chunks')
parser.add_argument('--patterns', nargs='+', default=[], help='正则模式（可多个）；默认搜 API 相关')
parser.add_argument('--out', default='api_hits.txt', help='输出文件，默认 api_hits.txt')
args = parser.parse_args()

chunks = glob.glob(os.path.join(args.chunk_dir, '*.js'))
print(f"Total chunks: {len(chunks)}")

patterns = args.patterns or [
    r'(?i)[a-z0-9/._:-]*(skland\.com|/api/)[a-z0-9/._:-]*',
]

all_hits = {}
for f in chunks:
    try:
        with open(f, encoding='utf-8', errors='ignore') as fh:
            c = fh.read()
    except Exception:
        continue
    for p in patterns:
        for m in re.findall(p, c):
            v = m.strip('"\'')
            if len(v) > 5 and not v.startswith('https://assets.') and not v.startswith('//'):
                all_hits.setdefault(v, set()).add(os.path.basename(f))

with open(args.out, 'w', encoding='utf-8') as out:
    for k in sorted(all_hits):
        out.write(f"{k}  <==  {','.join(sorted(all_hits[k]))}\n")

print(f"Unique hits: {len(all_hits)} -> {args.out}")
