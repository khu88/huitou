"""QR boundaries plus an independent macOS CoreImage decode of rendered SVG.

Roundtrip tests use only Apple's existing compiler/frameworks. They are skipped
when these are unavailable; no decoder packages or SDKs are installed.
"""
import base64
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qr_svg import MAX_BYTES, data_uri, matrix, svg


def _render_png(source):
    """Rasterize the emitted integer cell path, without an imaging dependency."""
    document = ET.fromstring(source)
    cells = document.find('{http://www.w3.org/2000/svg}path').attrib['d']
    points = re.findall(r'M(\d+) (\d+)h1v1h-1z', cells)
    if ''.join('M%s %sh1v1h-1z' % point for point in points) != cells:
        raise AssertionError('Unrecognized SVG path')
    grid = [[255] * 65 for _ in range(65)]
    for x, y in points:
        grid[int(y)][int(x)] = 0
    scale = 6
    scanlines = b''.join((b'\0' + bytes(value for value in row for _ in range(scale))) * scale for row in grid)

    def chunk(name, contents):
        return struct.pack('>I', len(contents)) + name + contents + struct.pack('>I', zlib.crc32(name + contents) & 0xffffffff)

    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', 390, 390, 8, 0, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))


class QRUnitTests(unittest.TestCase):
    def test_size_and_data_uri_are_self_contained(self):
        source = 'https://liteapp.weixin.qq.com/qr/test-token'
        modules = matrix(source)
        self.assertEqual(len(modules), 57)
        self.assertTrue(all(len(row) == 57 for row in modules))
        encoded = data_uri(source)
        self.assertTrue(encoded.startswith('data:image/svg+xml;base64,'))
        actual_svg = base64.b64decode(encoded.split(',', 1)[1]).decode('ascii')
        self.assertEqual(actual_svg, svg(source))
        self.assertNotIn('test-token', actual_svg)
        self.assertNotIn('<script', actual_svg)
        document = ET.fromstring(actual_svg)
        self.assertEqual(document.attrib['viewBox'], '0 0 65 65')
        self.assertEqual(document.find('{http://www.w3.org/2000/svg}rect').attrib['fill'], '#fff')

    def test_capacity_and_input_rejection(self):
        self.assertEqual(len(matrix('a' * MAX_BYTES)), 57)
        for invalid in ['', 'x' * (MAX_BYTES + 1), '微信', 'a\nb', None, 123]:
            with self.subTest(value=str(invalid)[:20]), self.assertRaises(ValueError):
                data_uri(invalid)

    def test_svg_does_not_interpolate_payload(self):
        payload = '"><script>alert(1)</script>'
        rendered = svg(payload)
        self.assertNotIn('<script', rendered)
        self.assertEqual(len(ET.fromstring(rendered)), 2)


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'),
                     'Independent QR decode needs existing macOS Swift/CoreImage')
class QRNativeDecodeTests(unittest.TestCase):
    def test_rendered_svg_roundtrips_with_coreimage(self):
        samples = [
            'https://liteapp.weixin.qq.com/qr/test-token',
            'https://weixin.qq.com/x?token=abc_DEF-0123%2Fxyz&next=1',
            'https://liteapp.weixin.qq.com/q/' + 'a' * 239,
            '0' * 271,
            'abcdefghijklmnopqrstuvwxyz0123456789' * 7,
        ]
        self.assertEqual(len(samples[2].encode('ascii')), 271)
        swift = '''
import Foundation
import CoreImage
let detector = CIDetector(ofType: CIDetectorTypeQRCode, context: CIContext(),
                         options: [CIDetectorAccuracy: CIDetectorAccuracyHigh])!
var results: [[String]] = []
for file in CommandLine.arguments.dropFirst() {
    guard let image = CIImage(contentsOf: URL(fileURLWithPath: file)) else { exit(2) }
    results.append(detector.features(in: image).compactMap {
        ($0 as? CIQRCodeFeature)?.messageString
    })
}
let encoded = try JSONSerialization.data(withJSONObject: results)
FileHandle.standardOutput.write(encoded)
'''
        with tempfile.TemporaryDirectory(prefix='conf-atlas-qr-test-') as directory:
            root = Path(directory)
            source = root / 'decode.swift'
            source.write_text(swift)
            binary = root / 'decode'
            compile_result = subprocess.run(
                [shutil.which('swiftc'), '-module-cache-path', str(root / 'cache'), str(source), '-o', str(binary)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            images = []
            for index, sample in enumerate(samples):
                image = root / ('qr-%d.png' % index)
                image.write_bytes(_render_png(svg(sample)))
                images.append(str(image))
            result = subprocess.run([str(binary)] + images, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            decoded = json.loads(result.stdout)
            self.assertEqual(decoded, [[sample] for sample in samples])


if __name__ == '__main__':
    unittest.main()
