#!/usr/bin/env python3
"""Run inside the pocket container: install one static visualization release with rollback metadata."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    root = Path('/var/www/pocketplay-blog')
    if not (root / 'current').is_dir():
        parser.error('Expected the active PocketPlay blog inside the pocket container.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/var/backups') / ('pi-rsi-blog-' + stamp)
    backup.mkdir(mode=0o700)
    release = root / 'interactive-releases' / (stamp + '-airline-20261004')
    release.mkdir(parents=True)
    with tarfile.open(args.archive) as archive:
        for member in archive.getmembers():
            name = Path(member.name)
            if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe archive member: ' + member.name)
        archive.extractall(release)
    for file in release.rglob('*'):
        file.chmod(0o755 if file.is_dir() else 0o644)
    release.chmod(0o755)
    for relative in ['zh/index.html', 'en/index.html', 'zh/wiki/index.html', 'en/tree/index.html', 'sitemap.xml']:
        if not (release / relative).is_file():
            raise ValueError('Incomplete release: ' + relative)
    target = root / 'current/rsi/interactive/airline-20261004'
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = str(target.readlink()) if target.is_symlink() else None
    if target.exists() and not target.is_symlink():
        raise ValueError('Refusing to replace an existing non-release directory: ' + str(target))
    robots = Path('/etc/nginx/pocketplay-robots/blog.txt')
    shutil.copy2(robots, backup / 'robots.txt')
    receipt = {'published_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'target': str(target), 'release': str(release), 'previous_target': previous,
               'backup': str(backup), 'sitemap': 'https://blog.pocketplay.win/rsi/interactive/airline-20261004/sitemap.xml'}
    (backup / 'deployment.json').write_text(json.dumps(receipt, indent=2))
    temporary = target.with_name(target.name + '.new')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(release)
    os.replace(temporary, target)
    line = 'Sitemap: ' + receipt['sitemap']
    old = robots.read_text()
    if line not in old:
        temp = robots.with_name(robots.name + '.new')
        temp.write_text(old.rstrip() + '\n\n' + line + '\n')
        temp.chmod(0o644)
        os.replace(temp, robots)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
