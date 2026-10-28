"""Dependency-free QR SVG for short ASCII login links, Model 2 version 10-L.

The fixed profile holds at most 271 bytes. Oversized/non-ASCII input raises
ValueError so the UI can keep its ordinary link fallback. No text is embedded
in SVG attributes, and no remote QR-generation service receives login secrets.

Reference: DENSO WAVE https://www.qrcode.com/en/about/version.html and the
Project Nayuki reference encoder (https://www.nayuki.io/page/qr-code-generator-library).
The placement/masking logic is adapted to a single fixed profile from that
MIT-licensed reference; its notice is preserved below.

Copyright (c) Project Nayuki. (MIT License)
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import base64
import itertools


SIZE = 57
MAX_BYTES = 271
DATA_WORDS = 274
ECC_WORDS = 18
BLOCK_LENGTHS = (68, 68, 69, 69)


def _multiply(a, b):
    result = 0
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a & 0x100:
            a ^= 0x11d
    return result


def _parity(data):
    generator = [1]
    root = 1
    for _ in range(ECC_WORDS):
        next_poly = [0] * (len(generator) + 1)
        for index, coefficient in enumerate(generator):
            next_poly[index] ^= coefficient
            next_poly[index + 1] ^= _multiply(coefficient, root)
        generator = next_poly
        root = _multiply(root, 2)
    work = list(data) + [0] * ECC_WORDS
    for index in range(len(data)):
        leading = work[index]
        for offset, coefficient in enumerate(generator):
            work[index + offset] ^= _multiply(leading, coefficient)
    return work[-ECC_WORDS:]


def _codewords(text):
    if not isinstance(text, str) or not text or not text.isascii():
        raise ValueError('QR link must be nonempty ASCII text')
    payload = text.encode('ascii')
    if len(payload) > MAX_BYTES or any(byte < 32 or byte == 127 for byte in payload):
        raise ValueError('QR link exceeds supported size or contains control characters')
    # Byte mode 0100; versions 10-40 use a 16-bit byte count.
    bits = '0100' + format(len(payload), '016b') + ''.join(format(byte, '08b') for byte in payload)
    bits += '0' * min(4, DATA_WORDS * 8 - len(bits))
    bits += '0' * (-len(bits) % 8)
    words = [int(bits[pos:pos + 8], 2) for pos in range(0, len(bits), 8)]
    for pad in itertools.cycle((0xec, 0x11)):
        if len(words) == DATA_WORDS:
            break
        words.append(pad)
    blocks, parities = [], []
    position = 0
    for count in BLOCK_LENGTHS:
        block = words[position:position + count]
        position += count
        blocks.append(block)
        parities.append(_parity(block))
    interleaved = [block[column] for column in range(69) for block in blocks if column < len(block)]
    interleaved += [block[column] for column in range(ECC_WORDS) for block in parities]
    assert len(interleaved) == 346
    return interleaved


def _bch(value, bits, polynomial):
    remainder = value << bits
    for position in range(remainder.bit_length() - 1, bits - 1, -1):
        if remainder & (1 << position):
            remainder ^= polynomial << (position - bits)
    return (value << bits) | remainder


def _format(matrix, reserved, mask):
    bits = _bch(8 | mask, 10, 0x537) ^ 0x5412  # Level L is binary 01.
    first = ([(8, y) for y in range(6)] + [(8, 7), (8, 8), (7, 8)] +
             [(x, 8) for x in range(5, -1, -1)])
    second = [(SIZE - 1 - x, 8) for x in range(8)] + [(8, y) for y in range(SIZE - 7, SIZE)]
    for coordinates in (first, second):
        for index, (x, y) in enumerate(coordinates):
            matrix[y][x] = bool((bits >> index) & 1)
            reserved[y][x] = True
    matrix[SIZE - 8][8] = True
    reserved[SIZE - 8][8] = True


def _template():
    matrix = [[False] * SIZE for _ in range(SIZE)]
    reserved = [[False] * SIZE for _ in range(SIZE)]

    def mark(x, y, dark):
        if 0 <= x < SIZE and 0 <= y < SIZE:
            matrix[y][x] = bool(dark)
            reserved[y][x] = True

    for i in range(SIZE):
        mark(6, i, i % 2 == 0)
        mark(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (SIZE - 4, 3), (3, SIZE - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                mark(cx + dx, cy + dy, max(abs(dx), abs(dy)) in (0, 1, 3))
    for cx in (6, 28, 50):
        for cy in (6, 28, 50):
            if (cx, cy) in ((6, 6), (6, 50), (50, 6)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    mark(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
    _format(matrix, reserved, 0)
    version = _bch(10, 12, 0x1f25)
    for index in range(18):
        a, b = SIZE - 11 + index % 3, index // 3
        mark(a, b, (version >> index) & 1)
        mark(b, a, (version >> index) & 1)
    return matrix, reserved


MASKS = (
    lambda x, y: (x + y) % 2,
    lambda x, y: y % 2,
    lambda x, y: x % 3,
    lambda x, y: (x + y) % 3,
    lambda x, y: (x // 3 + y // 2) % 2,
    lambda x, y: x * y % 2 + x * y % 3,
    lambda x, y: (x * y % 2 + x * y % 3) % 2,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2,
)


def _penalty(matrix):
    score = 0
    for line in list(matrix) + list(zip(*matrix)):
        for _, run in itertools.groupby(line):
            length = len(list(run))
            if length >= 5:
                score += length - 2
        text = ''.join('1' if bit else '0' for bit in line)
        for start in range(len(text) - 10):
            if text[start:start + 11] in ('10111010000', '00001011101'):
                score += 40
    for y in range(SIZE - 1):
        for x in range(SIZE - 1):
            if matrix[y][x] == matrix[y][x + 1] == matrix[y + 1][x] == matrix[y + 1][x + 1]:
                score += 3
    dark = sum(map(sum, matrix))
    score += abs(dark * 20 - SIZE * SIZE * 10) // (SIZE * SIZE) * 10
    return score


def matrix(text):
    """Return the 57-by-57 Boolean module matrix (quiet zone excluded)."""
    words = _codewords(text)
    modules, reserved = _template()
    payload = ''.join(format(byte, '08b') for byte in words)
    position = 0
    for right in range(SIZE - 1, 0, -2):
        if right <= 6:
            right -= 1
        rows = range(SIZE - 1, -1, -1) if (right + 1) & 2 == 0 else range(SIZE)
        for y in rows:
            for x in (right, right - 1):
                if not reserved[y][x]:
                    modules[y][x] = position < len(payload) and payload[position] == '1'
                    position += 1
    assert position == len(payload)
    best, best_score = None, None
    for mask, predicate in enumerate(MASKS):
        candidate = [[value ^ (not reserved[y][x] and predicate(x, y) == 0)
                      for x, value in enumerate(row)] for y, row in enumerate(modules)]
        _format(candidate, reserved, mask)
        score = _penalty(candidate)
        if best_score is None or score < best_score:
            best, best_score = candidate, score
    return best


def svg(text):
    modules = matrix(text)
    # Four-module white quiet zone. Path consists exclusively of integer cells.
    path = ''.join('M%d %dh1v1h-1z' % (x + 4, y + 4)
                   for y, row in enumerate(modules) for x, dark in enumerate(row) if dark)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 65 65" '
            'width="390" height="390" shape-rendering="crispEdges">'
            '<rect width="65" height="65" fill="#fff"/>'
            '<path fill="#000" d="' + path + '"/></svg>')


def data_uri(text):
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg(text).encode('ascii')).decode('ascii')
