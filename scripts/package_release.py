"""Build a release ZIP strictly from tracked files in the current commit."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import zipfile

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tag',required=True)
    parser.add_argument('--output',default='dist')
    args=parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+',args.tag):raise SystemExit('Expected a vMAJOR.MINOR.PATCH tag')
    root=Path(__file__).resolve().parents[1]
    toc=(root/'addon'/'lllucky'/'lllucky.toc').read_text(encoding='utf-8')
    version=re.search(r'^## Version:\s*(\S+)\s*$',toc,re.M)
    if not version or version.group(1)!=args.tag[1:]:raise SystemExit('Tag and addon version do not match')
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    archive=out/f'lllucky-{args.tag}-windows-x64.zip'
    subprocess.run(['git','archive','--format=zip',f'--prefix=lllucky-{args.tag}/',f'--output={archive}','HEAD'],cwd=root,check=True)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise RuntimeError('ZIP integrity check failed')
        files=z.namelist()
        for required in ['README.md','scripts/install.ps1','backend/headless.py','backend/worker.py','addon/lllucky/lllucky.toc']:
            if f'lllucky-{args.tag}/{required}' not in files:raise RuntimeError(f'Missing packaged file: {required}')
        forbidden=('.exe','.dll','.sav','.mpq','.log','.pid')
        if any(n.lower().endswith(forbidden) for n in files):raise RuntimeError('Unexpected game or runtime file in package')
        if any(n.endswith(('runtime-state.json','headless-state.json'))for n in files):raise RuntimeError('Runtime state must not be published')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
    print(f'Package: {archive.name} ({archive.stat().st_size} bytes)')
    print(f'SHA256: {digest}')

if __name__=='__main__':main()
