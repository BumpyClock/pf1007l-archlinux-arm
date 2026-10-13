#!/usr/bin/env python3
"""Print changed DT property names without exposing their values."""
import argparse
from pathlib import Path
import struct


def properties(path):
    data = path.read_bytes()
    magic, size, offset, strings, *_ = struct.unpack_from(">10I", data)
    assert magic == 0xd00dfeed and size <= len(data)
    stack = []
    result = {}
    while True:
        token, = struct.unpack_from(">I", data, offset)
        offset += 4
        if token == 1:
            end = data.index(b"\0", offset)
            stack.append(data[offset:end].decode())
            offset = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, name = struct.unpack_from(">2I", data, offset)
            offset += 8
            start = strings + name
            name = data[start:data.index(b"\0", start)].decode()
            result["/".join(stack) + "/" + name] = data[offset:offset+length]
            offset = (offset + length + 3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            break
        else:
            raise ValueError("Invalid DT token")
    return result

def metadata(path):
    data = path.read_bytes()
    fields = struct.unpack_from(">10I", data)
    offset = fields[4]
    reservations = []
    while True:
        address, size = struct.unpack_from(">2Q", data, offset)
        offset += 16
        if address == size == 0:
            break
        reservations.append((address, size))
    return fields[5:8], reservations


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    args = parser.parse_args()
    old, new = properties(args.old), properties(args.new)
    print("removed=" + repr(sorted(old.keys() - new.keys())))
    print("added=" + repr(sorted(new.keys() - old.keys())))
    print("changed=" + repr(sorted(key for key in old.keys() & new.keys() if old[key] != new[key])))
    print("boot_metadata_equal=" + str(metadata(args.old) == metadata(args.new)))
