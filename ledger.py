"""Local, reviewable file changes for human-supervised assistants (Python 3.10+)."""
import argparse, difflib, hashlib, json, os, tempfile
from pathlib import Path

class Conflict(ValueError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None

def target(root, relative):
    p = Path(relative)
    if p.is_absolute() or not p.parts or '..' in p.parts or p.parts[0] == '.ledger':
        raise Conflict('Unsafe or reserved path: ' + str(relative))
    result = root / p
    for parent in [result, *result.parents]:
        if parent == root: break
        if parent.is_symlink(): raise Conflict('Symlinks are forbidden')
    if not result.resolve().is_relative_to(root.resolve()): raise Conflict('Path escapes root')
    if result.exists() and not result.is_file(): raise Conflict('Not a regular file')
    return result

def read(path):
    return path.read_bytes() if path.exists() else None

def atomic(path, content):
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.ledger-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out: out.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)

def inspect(root, plan):
    if plan.get('version') != 1 or not isinstance(plan.get('changes'), list):
        raise Conflict('Expected version 1 and changes list')
    if not 1 <= len(plan['changes']) <= 100: raise Conflict('Expected 1..100 changes')
    seen, prepared = set(), []
    for change in plan['changes']:
        p = target(root, change['path'])
        if str(p.resolve()) in seen: raise Conflict('Duplicate path')
        seen.add(str(p.resolve()))
        before = read(p)
        if 'expected_sha256' not in change or digest(before) != change['expected_sha256']:
            raise Conflict('Stale precondition: ' + change['path'])
        if 'content' not in change: raise Conflict('Explicit content required (null means delete)')
        content = change['content']
        if content is not None and not isinstance(content, str): raise Conflict('Content must be text or null')
        after = content.encode('utf-8') if content is not None else None
        if max(len(before or b''), len(after or b'')) > 1_000_000: raise Conflict('File exceeds 1 MB')
        try: (before or b'').decode('utf-8')
        except UnicodeDecodeError: raise Conflict('Only UTF-8 text supported')
        prepared.append((change['path'], p, before, after))
    return prepared

def preview(root, plan):
    output=[]
    for name, _, before, after in inspect(root, plan):
        output.append(f'{name}: {digest(before)} -> {digest(after)}\n')
        output.extend(difflib.unified_diff((before or b'').decode().splitlines(True), (after or b'').decode().splitlines(True), fromfile=name+' (before)', tofile=name+' (after)'))
    return ''.join(output)

def state_dir(root):
    d=root / '.ledger'
    if d.is_symlink(): raise Conflict('Journal symlinks forbidden')
    d.mkdir(exist_ok=True, mode=0o700)
    return d

def apply(root, plan):
    prepared=inspect(root, plan)
    d=state_dir(root)
    lock=d/'lock'
    try: fd=os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    except FileExistsError: raise Conflict('Ledger locked; inspect existing transaction before recovery')
    os.close(fd)
    journal=None
    try:
        prepared=inspect(root, plan)
        record={'version':1,'status':'prepared','changes':[{'path':n,'before':b.decode() if b is not None else None,'after_sha256':digest(a)} for n,p,b,a in prepared]}
        fd,name=tempfile.mkstemp(prefix='tx-',suffix='.json',dir=d); os.close(fd)
        journal=Path(name)
        atomic(journal,json.dumps(record,indent=2).encode()); journal.chmod(0o600)
        done=[]
        try:
            for n,p,b,a in prepared:
                if digest(read(p)) != digest(b): raise Conflict('Concurrent edit: '+n)
                atomic(p,a); done.append((p,b,a))
        except Exception:
            for p,b,a in reversed(done):
                if digest(read(p)) == digest(a): atomic(p,b)
            record['status']='failed'; atomic(journal,json.dumps(record,indent=2).encode())
            raise
        record['status']='applied'; atomic(journal,json.dumps(record,indent=2).encode())
        return journal
    finally: lock.unlink(missing_ok=True)

def undo(root, journal):
    d=state_dir(root).resolve()
    j=Path(journal)
    if j.is_symlink() or j.resolve().parent != d: raise Conflict('Journal must be directly inside root/.ledger')
    record=json.loads(j.read_text())
    if record.get('status')!='applied': raise Conflict('Only applied transactions can be undone')
    plan={'version':1,'changes':[{'path':c['path'],'expected_sha256':c['after_sha256'],'content':c['before']} for c in record['changes']]}
    result=apply(root,plan)
    record['status']='undone'; atomic(j,json.dumps(record,indent=2).encode())
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    for cmd in ['preview','apply']:
        p=sub.add_parser(cmd); p.add_argument('plan',type=Path)
        if cmd=='apply': p.add_argument('--approve',action='store_true',required=True)
    p=sub.add_parser('undo'); p.add_argument('journal',type=Path); p.add_argument('--approve',action='store_true',required=True)
    a=parser.parse_args(); root=a.root.resolve()
    if not root.is_dir(): parser.error('Root must be an existing directory')
    try:
        if a.command=='undo': print(undo(root,a.journal))
        else:
            plan=json.loads(a.plan.read_text())
            print(preview(root,plan) if a.command=='preview' else apply(root,plan))
    except (Conflict,KeyError,TypeError,json.JSONDecodeError) as e: parser.exit(2,str(e)+'\n')

if __name__=='__main__': main()
