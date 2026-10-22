import argparse
import unittest
from unittest.mock import Mock, patch

import hotas_fusion as fusion


class DiscoveryTests(unittest.TestCase):
    def device(self, name, path):
        device = Mock()
        device.name = name
        device.path = path
        return device

    def test_name_discovery_ignores_event_number(self):
        for path in ('/dev/input/event2', '/dev/input/event91'):
            stick = self.device('Thustmaster Joystick - HOTAS Warthog', path)
            with patch.object(fusion, 'list_devices', return_value=[path]), patch.object(fusion, 'InputDevice', return_value=stick):
                self.assertIs(fusion.find_device(fusion.STICK_TOKENS), stick)

    def test_explicit_name_is_normalized(self):
        throttle = self.device('Thrustmaster Throttle - HOTAS Warthog', 'arbitrary')
        with patch.object(fusion, 'list_devices', return_value=['arbitrary']), patch.object(fusion, 'InputDevice', return_value=throttle):
            self.assertIs(fusion.find_device(fusion.THROTTLE_TOKENS, 'THRUSTMASTER throttle hotas   warthog'), throttle)

    def test_disappearing_device_does_not_abort_scan(self):
        stick = self.device('Thustmaster Joystick - HOTAS Warthog', 'present')
        with patch.object(fusion, 'list_devices', return_value=['gone', 'present']), patch.object(fusion, 'InputDevice', side_effect=[FileNotFoundError(), stick]):
            self.assertIs(fusion.find_device(fusion.STICK_TOKENS), stick)

    def test_duplicate_names_fail_and_close_handles(self):
        devices = [self.device('Joystick HOTAS Warthog', str(i)) for i in range(2)]
        with patch.object(fusion, 'list_devices', return_value=['a', 'b']), patch.object(fusion, 'InputDevice', side_effect=devices):
            with self.assertRaisesRegex(RuntimeError, 'lebih dari satu'):
                fusion.find_device(fusion.STICK_TOKENS)
        for device in devices:
            device.close.assert_called_once()

    def test_missing_throttle_closes_stick(self):
        stick = self.device('Joystick HOTAS Warthog', 'stick')
        with patch.object(fusion, 'find_device', side_effect=[stick, RuntimeError('missing throttle')]):
            with self.assertRaises(RuntimeError):
                fusion.open_sources(argparse.Namespace(stick=None, throttle=None))
        stick.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
