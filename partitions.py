#!/usr/bin/env python3
"""Back up and restore the physical firmware partitions listed for this SM-S918B."""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLOCK = 4096
LIMIT = 1_000_000_000
LAST_LBA = (62275583, 5119, 5119, 8191, 163839, 8191)
CHUNK = 64 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Partition:
    lun: int
    entry: int
    name: str
    first: int
    last: int
    scope: str

    @property
    def size(self):
        return (self.last - self.first + 1) * BLOCK

    @property
    def address(self):
        return f'{self.lun}/{self.name}'


def partition_map():
    with (ROOT / 'partitions/physical.csv').open() as stream:
        rows = []
        for r in csv.DictReader(stream):
            p = Partition(int(r['lun']), int(r['entry']), r['name'], int(r['first_lba']),
                          int(r['last_lba']), r['scope'])
            require(p.first * BLOCK == int(r['offset_bytes']) and p.size == int(r['size_bytes']),
                    f'Inconsistent partition map for {p.name}')
            rows.append(p)
        return rows


def image_path(folder, p):
    return folder / 'images' / (p.name + '.img')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def qdl(*commands):
    usb = subprocess.run(['lsusb', '-d', '05c6:9008'], capture_output=True, text=True)
    require(len(usb.stdout.splitlines()) == 1, 'Connect one phone in EDL mode.')
    result = subprocess.run([ROOT / '.tools/qdl', '--quiet', '--backend=usb', '--storage=ufs',
                             '--skip-reset', ROOT / 'loader/sm-s918b-bit-a-firehose.elf', *commands],
                            capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout).strip() or 'QDL failed.')
    hashes = re.findall(r'(?im)^([a-f0-9]{64})[ \t]*$', result.stdout)
    require(len(hashes) == 1, 'QDL did not return one device digest.')
    return hashes[0].lower()


def table_header(sector, lun, backup):
    last = LAST_LBA[lun]
    expected = (last, 1) if backup else (1, last)
    require(sector[:8] == b'EFI PART' and len(sector) == BLOCK, f'Missing GPT on LUN {lun}')
    length, crc = struct.unpack_from('<II', sector, 12)
    header = bytearray(sector[:length])
    require(92 <= length <= BLOCK, 'Invalid GPT header size')
    struct.pack_into('<I', header, 16, 0)
    require(zlib.crc32(header) == crc, 'GPT header checksum mismatch')
    require(struct.unpack_from('<QQQQ', header, 24) == (*expected, 6, last - 9),
            f'LUN {lun} geometry differs from this profile')
    start, count, size, table_crc = struct.unpack_from('<QIII', header, 72)
    require(start == (last - 8 if backup else 2) and 0 < count <= 128 and size == 128,
            'Unsupported GPT entry layout')
    return header[56:72], count * size, table_crc


def gpt_parts(lun):
    yield 'primary', 0, 6
    yield 'secondary', LAST_LBA[lun] - 8, 9


def layout_path(folder, lun, side):
    return folder / 'layout' / f'lun{lun}-{side}.bin'


def check_layout(folder, rows):
    for lun in range(len(LAST_LBA)):
        copies = []
        for side, _, count in gpt_parts(lun):
            data = layout_path(folder, lun, side).read_bytes()
            require(len(data) == count * BLOCK, 'Incomplete GPT copy')
            secondary = side == 'secondary'
            sector = data[-BLOCK:] if secondary else data[BLOCK:2 * BLOCK]
            guid, length, crc = table_header(sector, lun, secondary)
            offset = 0 if secondary else 2 * BLOCK
            entries = data[offset:offset + length]
            require(zlib.crc32(entries) == crc, 'GPT entry checksum mismatch')
            copies.append((guid, entries))
        require(copies[0] == copies[1], f'GPT copies differ on LUN {lun}')
        found = []
        for index in range(0, len(entries), 128):
            entry = entries[index:index + 128]
            if any(entry[:16]):
                name = entry[56:128].decode('utf-16le').rstrip('\0')
                found.append((index // 128 + 1, name, *struct.unpack_from('<QQ', entry, 32)))
        expected = [(p.entry, p.name, p.first, p.last) for p in rows if p.lun == lun]
        require(found == expected, f'Partition map differs on LUN {lun}')


def read_range(lun, start, size, dest):
    address = f'{lun}/{start}+{size // BLOCK}'
    expected = qdl('read', address, dest, 'sha256', address)
    require(dest.stat().st_size == size and digest(dest) == expected, f'Incomplete read at {address}')


def backup(folder, rows, selected):
    folder.mkdir(mode=0o700, parents=True)
    print(f'Backup folder: {folder}', flush=True)
    (folder / 'images').mkdir()
    (folder / 'layout').mkdir()
    verified = {}
    with tempfile.TemporaryDirectory(dir=folder) as work:
        chunk = Path(work) / 'chunk'
        for lun in range(len(LAST_LBA)):
            read_range(lun, 1, BLOCK, chunk)
            table_header(chunk.read_bytes(), lun, False)
            for side, start, count in gpt_parts(lun):
                read_range(lun, start, count * BLOCK, layout_path(folder, lun, side))
        check_layout(folder, rows)
        shutil.copyfile(ROOT / 'partitions/physical.csv', folder / 'layout/physical.csv')
        for p in selected:
            print(f'Reading {p.name} ({p.size:,} bytes)', flush=True)
            pending = Path(work) / 'image'
            with pending.open('wb') as out:
                for off in range(0, p.size, CHUNK):
                    read_range(p.lun, p.first + off // BLOCK, min(CHUNK, p.size - off), chunk)
                    with chunk.open('rb') as source:
                        shutil.copyfileobj(source, out)
            verified[p.name] = digest(pending)
            pending.replace(image_path(folder, p))
    manifest = folder / 'verified.json'
    pending_manifest = manifest.with_suffix('.tmp')
    pending_manifest.write_text(json.dumps(verified, indent=2) + '\n')
    pending_manifest.replace(manifest)
    print(f'Verified {len(verified)} firmware images.')


def verify_backup(folder, rows, selected):
    check_layout(folder, rows)
    manifest = json.loads((folder / 'verified.json').read_text())
    require(set(manifest) == {p.name for p in selected}, 'Incomplete firmware backup')
    for p in selected:
        image = image_path(folder, p)
        require(image.is_file() and image.stat().st_size == p.size and digest(image) == manifest[p.name],
                f'Backup image differs for {p.name}')
    return manifest


def confirm(phrase):
    require(sys.stdin.isatty(), 'Interactive terminal confirmation is required.')
    require(input(f'Type {phrase} to continue: ') == phrase, 'Cancelled.')


def rebuild(folder, dest, selected, manifest):
    require(not dest.exists(), f'Output already exists: {dest}')
    print(f'Create six sparse disk images in {dest.resolve()}.')
    confirm('REBUILD SM-S918B')
    with tempfile.TemporaryDirectory(prefix='.rebuild-', dir=dest.parent) as staging:
        for lun, last in enumerate(LAST_LBA):
            with (Path(staging) / f'lun{lun}.img').open('xb') as disk:
                disk.truncate((last + 1) * BLOCK)
                for side, start, _ in gpt_parts(lun):
                    disk.seek(start * BLOCK)
                    disk.write(layout_path(folder, lun, side).read_bytes())
                for p in selected:
                    if p.lun == lun:
                        disk.seek(p.first * BLOCK)
                        with image_path(folder, p).open('rb') as source:
                            checksum = hashlib.sha256()
                            while data := source.read(1024 * 1024):
                                disk.write(data)
                                checksum.update(data)
                        require(checksum.hexdigest() == manifest[p.name], f'Image changed: {p.name}')
        # Reserve the name, then publish all six files with one rename.
        dest.mkdir(mode=0o700)
        try:
            os.replace(staging, dest)
        except OSError:
            dest.rmdir()
            raise
    print(f'Rebuilt six local disk images in {dest}.')


def verify_live_layout(folder):
    for lun in range(len(LAST_LBA)):
        for side, start, count in gpt_parts(lun):
            require(qdl('sha256', f'{lun}/{start}+{count}') == digest(layout_path(folder, lun, side)),
                    f'Connected device differs from this backup on LUN {lun}.')


def restore(folder, targets, manifest):
    require(sys.stdin.isatty(), 'Interactive terminal confirmation is required.')
    print(f'Backup: {folder.resolve()}')
    verify_live_layout(folder)
    # Compare in modest requests so the loader can finish each digest.
    pending = []
    for p in targets:
        source = image_path(folder, p)
        with source.open('rb') as stream:
            for off in range(0, p.size, CHUNK):
                data = stream.read(min(CHUNK, p.size - off))
                address = f'{p.lun}/{p.first + off // BLOCK}+{len(data) // BLOCK}'
                if qdl('sha256', address) != hashlib.sha256(data).hexdigest():
                    pending.append(p)
                    break
    if not pending:
        print('All selected partitions already match the backup.')
        return
    print('Partitions to write: ' + ', '.join(p.name for p in pending))
    confirm(f'RESTORE SM-S918B {targets[0].name if len(targets) == 1 else "ALL"}')
    verify_live_layout(folder)
    with tempfile.TemporaryDirectory() as work:
        staged = Path(work) / 'image'
        for p in pending:
            shutil.copyfile(image_path(folder, p), staged)
            require(staged.stat().st_size == p.size and digest(staged) == manifest[p.name],
                    f'Image changed: {p.name}')
            print(f'Writing {p.name}', flush=True)
            actual = qdl('write', p.address, staged, 'sha256', p.address)
            require(actual == manifest[p.name], f'Device verification failed for {p.name}')
            print(f'Verified {p.name}', flush=True)


def main():
    os.umask(0o077)
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest='action', required=True)
    for action in ('backup', 'plan', 'rebuild', 'restore'):
        parser = commands.add_parser(action)
        parser.add_argument('folder', type=Path, help='local backup directory')
        if action == 'rebuild':
            parser.add_argument('output', type=Path, help='new directory for sparse disk images')
        if action == 'restore':
            parser.add_argument('partition', help='one firmware partition name or ALL')
    args = cli.parse_args()
    rows = partition_map()
    selected = [p for p in rows if p.scope == 'firmware' and 0 < p.size <= LIMIT]
    require(selected and len({p.name for p in selected}) == len(selected), 'Invalid firmware selection')
    if args.action == 'backup':
        return backup(args.folder, rows, selected)
    manifest = verify_backup(args.folder, rows, selected)
    if args.action == 'plan':
        for p in selected:
            print(f'{p.name:16} LUN {p.lun}  LBA {p.first:9}–{p.last:<9}  {p.size:12,} bytes')
        print(f'{len(selected)} partitions, {sum(p.size for p in selected):,} bytes in total.')
    elif args.action == 'rebuild':
        rebuild(args.folder, args.output, selected, manifest)
    else:
        targets = [p for p in selected if args.partition in (p.name, 'ALL')]
        require(targets, 'Choose a firmware partition from the plan.')
        restore(args.folder, targets, manifest)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, EOFError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
    except KeyboardInterrupt:
        sys.exit('Interrupted.')
