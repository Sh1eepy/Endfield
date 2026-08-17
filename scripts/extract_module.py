import os, re, glob, argparse


def extract_full_module(chunk_file, module_id):
    """从 chunk 文件中提取指定 webpack 模块的完整定义（找下一个模块边界）。"""
    with open(chunk_file, encoding='utf-8', errors='ignore') as f:
        c = f.read()
    start = c.find(f'{module_id}:function(')
    if start < 0:
        return None
    nxt = re.search(r',\d+:function\(', c[start + 1:])
    end = start + 1 + nxt.start() if nxt else len(c)
    return c[start:end]


parser = argparse.ArgumentParser(description='从 webpack chunk 目录提取指定模块的完整代码')
parser.add_argument('--chunk-dir', default='chunks', help='chunk 目录，默认 ./chunks')
parser.add_argument('--module-id', nargs='+', required=True, help='模块ID，可传多个，如 71188 94976')
parser.add_argument('--out-dir', default='.', help='输出目录，默认当前目录，输出为 mod{id}.txt')
args = parser.parse_args()

for module_id in args.module_id:
    found = False
    for f in sorted(glob.glob(os.path.join(args.chunk_dir, '*.js'))):
        with open(f, encoding='utf-8', errors='ignore') as fh:
            c = fh.read()
        if f'{module_id}:function(' in c:
            mod = extract_full_module(f, module_id)
            outname = os.path.join(args.out_dir, f'mod{module_id}.txt')
            with open(outname, 'w', encoding='utf-8') as out:
                out.write(mod or '')
            print(f'module {module_id} in {os.path.basename(f)}, len={len(mod) if mod else 0} -> {outname}')
            found = True
            break
    if not found:
        print(f'module {module_id} not found')
