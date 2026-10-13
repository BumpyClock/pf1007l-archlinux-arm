"""Read and rewrite bounded Linux newc archives."""

def members(data):
    offset = 0
    while offset < len(data):
        header = data[offset:offset + 110]
        if len(header) != 110 or header[:6] != b'070701':
            raise ValueError('Invalid newc archive')
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        end_name = offset + 110 + fields[11]
        if fields[11] < 1 or data[end_name - 1:end_name] != b'\0':
            raise ValueError('Invalid newc member name')
        name = data[offset + 110:end_name - 1].decode()
        body = (end_name + 3) & ~3
        end_body = body + fields[6]
        if end_body > len(data):
            raise ValueError('Truncated newc member')
        next_offset = (end_body + 3) & ~3
        yield name, fields, data[body:end_body], data[offset:next_offset]
        offset = next_offset
        if name == 'TRAILER!!!':
            if any(data[offset:]):
                raise ValueError('Data after newc trailer')
            return
    raise ValueError('Missing newc trailer')


def entry(name, fields, body):
    fields = list(fields)
    encoded = name.encode() + b'\0'
    fields[6], fields[11], fields[12] = len(body), len(encoded), 0
    data = b'070701' + b''.join(f'{value:08x}'.encode() for value in fields) + encoded
    data += b'\0' * (-len(data) % 4)
    data += body
    return data + b'\0' * (-len(data) % 4)

