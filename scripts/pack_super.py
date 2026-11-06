#!/usr/bin/env python3
"""Repack a raw gaokun super, retaining measured liblp geometry and group layout.

Only four A-slot extents are relocated. Empty B partitions, metadata slots,
virtual-A/B flags, device size and allocation limits come from the live device.
Geometry, header and table checksums are verified before repacking.
"""
import hashlib
import argparse
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'out'
ALIGN = 1024 * 1024

def align(value):
    return (value + ALIGN - 1) // ALIGN * ALIGN

def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--report-dir', type=Path, default=ROOT / 'reports')
    args = parser.parse_args()
    OUT = args.output.resolve()
    template = (ROOT / 'input/super-metadata.bin').read_bytes()
    geometry = template[4096:8192]
    assert struct.unpack_from('<I', geometry)[0] == 0x616c4467
    geo = bytearray(geometry[:52])
    expected = bytes(geo[8:40]); geo[8:40] = bytes(32)
    assert hashlib.sha256(geo).digest() == expected
    max_size, slots, block = struct.unpack_from('<III', geometry, 40)
    assert (max_size, slots, block) == (65536, 3, 4096)
    data = template[12288:12288 + max_size]
    magic, major, minor, header_size = struct.unpack_from('<IHHI', data)
    assert (magic, major, minor) == (0x414c5030, 10, 2)
    header = bytearray(data[:header_size])
    checksum = bytes(header[12:44]); header[12:44] = bytes(32)
    assert hashlib.sha256(header).digest() == checksum
    table_size = struct.unpack_from('<I', header, 44)[0]
    tables = bytearray(data[header_size:header_size + table_size])
    assert hashlib.sha256(tables).digest() == header[48:80]
    descriptors = [struct.unpack_from('<III', header, 80 + i * 12) for i in range(4)]
    poff, pcount, psize = descriptors[0]
    eoff, ecount, esize = descriptors[1]
    goff, gcount, gsize = descriptors[2]
    boff, bcount, bsize = descriptors[3]
    assert (pcount, psize, ecount, esize, gcount, gsize, bcount, bsize) == (8, 52, 4, 24, 3, 48, 1, 64)
    first_sector, alignment, alignment_offset, super_size, name, flags = struct.unpack_from('<QIIQ36sI', tables, boff)
    assert name.split(b'\0')[0] == b'super' and super_size == 12884901888
    cursor = first_sector * 512
    parts = []
    used = 0
    for i in range(pcount):
        name, attr, first, count, group = struct.unpack_from('<36sIIII', tables, poff + i * psize)
        name = name.split(b'\0')[0].decode()
        if name.endswith('_b'):
            assert count == 0
            continue
        assert name.endswith('_a') and count == 1
        image = OUT / (name[:-2] + '.img')
        size = image.stat().st_size
        assert size > 0 and size % block == 0
        cursor = align(cursor)
        struct.pack_into('<QIQI', tables, eoff + first * esize, size // 512, 0, cursor // 512, 0)
        parts.append(dict(name=name, attributes=attr, image=image.name, offset=cursor, size=size))
        cursor += size
        used += size
    group_limit = struct.unpack_from('<Q', tables, goff + gsize + 40)[0]
    assert used <= group_limit and cursor <= super_size
    header[48:80] = hashlib.sha256(tables).digest()
    header[12:44] = bytes(32)
    header[12:44] = hashlib.sha256(header).digest()
    metadata = (header + tables).ljust(max_size, b'\0')
    output = OUT / 'super.raw.img'
    with output.open('wb') as target:
        target.truncate(super_size)
        target.seek(4096)
        target.write(geometry * 2)
        target.write(metadata * (slots * 2))
        for part in parts:
            target.seek(part['offset'])
            with (OUT / part['image']).open('rb') as source:
                while chunk := source.read(8 * ALIGN):
                    target.write(chunk)
    metadata_image = args.report_dir / 'candidate-super-metadata.bin'
    with output.open('rb') as source:
        metadata_image.write_bytes(source.read(ALIGN))
    (args.report_dir / 'super-layout.json').write_text(json.dumps(dict(
        super_size=super_size, metadata_max_size=max_size, metadata_slots=slots,
        header_version=f'{major}.{minor}', header_flags=struct.unpack_from('<I', header, 128)[0],
        group_limit=group_limit, allocated_size=used, partitions=parts), indent=2))
    print(f'Packed {output}: {super_size} bytes, {used} bytes allocated')

if __name__ == '__main__':
    main()
