#!/usr/bin/env python3
"""Extract the pinned panel and Silead inputs from user-supplied Android modules."""
import argparse
import hashlib
from pathlib import Path
import struct

LCD_SHA = '85d2fe6cbed6c6177d30f142233c6f0a0d1ce613789a3e7999649bbe2ce492d1'
TOUCH_SHA = 'b4e0398c04e38f11870e2757d25e2259e1877e5684613eb588dc35f254badd15'
PANEL_SHA = '25caf7b980d3cdaddc6cd1da7a74bd4bb747385b3a5461e918ec0abb96c89a2e'
HEADER_SHA = 'd7412abb703bdd7927b610f36f1451c6ceafdf6ad6fc8cc7476d6e8efdf3cc72'
FIRMWARE_SHA = 'e11ffa8a33a56b78f8d2f57925fef1b67ea9a58c264bb5f3a8553ea52b14a9e6'


def symbol_bytes(path, expected_hash, symbol_name, expected_size):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError('Stock module hash differs; this extractor supports the pinned board revision')
    if data[:7] != b'\x7fELF\x01\x01\x01' or len(data) < 52:
        raise ValueError('A little-endian ELF32 module is required')
    offset = struct.unpack_from('<I', data, 32)[0]
    width, count = struct.unpack_from('<HH', data, 46)
    if width != 40 or offset + count * width > len(data):
        raise ValueError('Invalid ELF section table')
    sections = [struct.unpack_from('<10I', data, offset + index * width) for index in range(count)]
    matches = []
    for section in sections:
        if section[1] != 2:
            continue
        if section[9] != 16 or section[6] >= count or section[5] % 16:
            raise ValueError('Invalid ELF symbol table')
        strings_section = sections[section[6]]
        strings = data[strings_section[4]:strings_section[4] + strings_section[5]]
        end = section[4] + section[5]
        if end > len(data):
            raise ValueError('Truncated ELF symbol table')
        for position in range(section[4], end, 16):
            name, value, size, _, _, index = struct.unpack_from('<IIIBBH', data, position)
            if name >= len(strings):
                raise ValueError('Invalid ELF symbol name')
            name_end = strings.find(b'\0', name)
            if name_end < 0:
                raise ValueError('Unterminated ELF symbol name')
            if strings[name:name_end].decode(errors='strict') != symbol_name:
                continue
            if size != expected_size:
                continue
            if index >= count:
                raise ValueError('Pinned symbol section differs')
            owner = sections[index]
            start = owner[4] + value - owner[3]
            if start < owner[4] or start + size > owner[4] + owner[5] or start + size > len(data):
                raise ValueError('Symbol extends beyond its section')
            matches.append(data[start:start + size])
    if len(matches) != 1:
        raise ValueError('Expected one matching symbol')
    return matches[0]


def panel_header(table):
    if len(table) != 204 * 72 or hashlib.sha256(table).hexdigest() != PANEL_SHA:
        raise ValueError('Panel command table differs')
    lines = ['/* PRIVATE local extracted panel data; do not redistribute. */',
             'static const struct sq9365_record sq9365_program[] = {']
    for index in range(204):
        command, length = struct.unpack_from('<II', table, index * 72)
        payload = table[index * 72 + 8:index * 72 + 72]
        if command <= 255 and length <= 64:
            values = ', '.join(f'0x{value:02x}' for value in payload[:length]) or '0'
            lines.append(f'\t{{ SQ9365_DCS, 0, 0x{command:02x}, {length}, {{ {values} }} }},')
        elif command == 0xff0 and 0 < length <= 65535:
            lines.append(f'\t{{ SQ9365_DELAY, {length}, 0, 0, {{ 0 }} }},')
        elif command == 0xff1 and index == 203:
            lines.append('\t{ SQ9365_END, 0, 0, 0, { 0 } },')
        else:
            raise ValueError('Invalid panel command')
    result = ('\n'.join(lines + ['};', ''])).encode()
    if hashlib.sha256(result).hexdigest() != HEADER_SHA:
        raise ValueError('Generated panel header differs')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lcd-module', required=True, type=Path)
    parser.add_argument('--touch-module', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New private directory outside Git')
    args = parser.parse_args()
    panel = symbol_bytes(args.lcd_module, LCD_SHA, 'wjwx8006a_initialization', 14688)
    firmware = symbol_bytes(args.touch_module, TOUCH_SHA, 'GSLX680_FW_M86HD', 36960)
    if hashlib.sha256(firmware).hexdigest() != FIRMWARE_SHA:
        raise ValueError('Silead firmware differs')
    records = list(struct.iter_unpack('<II', firmware))
    if any(offset > 0xf0 or offset % 4 for offset, _ in records) or sum(offset == 0xf0 for offset, _ in records) != 140:
        raise ValueError('Silead register format differs')
    header = panel_header(panel)
    if args.output.exists():
        raise ValueError('Use a new private output directory')
    args.output.mkdir(parents=True, mode=0o700)
    (args.output / 'sq9365-private-table.h').write_bytes(header)
    destination = args.output / 'silead/pf1007l-gsl-m86-hd.fw'
    destination.parent.mkdir(mode=0o700)
    destination.write_bytes(firmware)
    print('Verified panel header and Silead firmware extracted into the private output directory')


if __name__ == '__main__':
    main()
