"""Opt-in scaffold files, restricted to the first approved step's ownership."""
import argparse
import hashlib
import json
from pathlib import Path

from execution_options import option

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'
FILES = ('package.json', 'vite.config.js', 'playwright.config.js', '.gitignore')


def apply(root, name, owned):
    if name != 'vite-react':
        raise ValueError('Unknown scaffold template: ' + name)
    template_name = name
    root = Path(root)
    state = root / '.uncle/workflow'
    receipt = state / 'scaffold-template.json'
    if receipt.exists():
        if json.loads(receipt.read_text()).get('template') != name:
            raise ValueError('A different scaffold template was already applied')
        return []
    if '*' not in owned and not set(FILES) <= set(owned):
        raise ValueError('Scaffold template requires first-step ownership of: ' + ', '.join(FILES))
    contents = {name: (TEMPLATES / 'vite-react' / name).read_bytes() for name in FILES}
    for name, data in contents.items():
        target = root / name
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.read_bytes() != data)):
            raise ValueError('Scaffold template refuses to overwrite ' + name)
    written = []
    for name, data in contents.items():
        target = root / name
        if not target.exists():
            with target.open('xb') as stream:
                stream.write(data)
            written.append(name)
    state.mkdir(parents=True, exist_ok=True)
    (state / 'scaffold-verification-commands.txt').write_bytes(
        (TEMPLATES / 'vite-react/verification-commands.txt').read_bytes())
    receipt.write_text(json.dumps({'template': template_name, 'files': {
        name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}, indent=2) + '\n')
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ownership-file', required=True)
    args = parser.parse_args()
    name = option('scaffold-template', '')
    if not name:
        return 0
    owned = [row.split('\t', 1)[1] for row in Path(args.ownership_file).read_text().splitlines()
             if row.startswith('1\t')]
    try:
        files = apply('.', name, owned)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print('Scaffold template %s: %s; verification commands: .uncle/workflow/scaffold-verification-commands.txt' %
          (name, ', '.join(files) or 'already applied'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
