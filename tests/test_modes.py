import unittest
from unittest.mock import Mock
from evdev import ecodes
from hotas_fusion import GroundFlightRouter, write_mode_axes


class ModeTests(unittest.TestCase):
    def router(self):
        return GroundFlightRouter('stick', ecodes.BTN_PINKIE, 0, 65534, 32767)

    def test_routing_and_neutral_output(self):
        router = self.router()
        router.value = 65534
        self.assertEqual(router.outputs(), (32767, 0))
        router.value = 32767
        self.assertTrue(router.toggle(1))
        router.value = 0
        self.assertEqual(router.outputs(), (0, -32767))
        virtual = Mock()
        write_mode_axes(virtual, router)
        self.assertEqual([call.args for call in virtual.write.call_args_list], [
            (ecodes.EV_ABS, ecodes.ABS_X, 0),
            (ecodes.EV_ABS, ecodes.ABS_RX, -32767)])

    def test_press_edge_only_and_return_to_flight(self):
        router = self.router()
        self.assertTrue(router.toggle(1))
        self.assertFalse(router.toggle(1))
        self.assertFalse(router.toggle(2))
        router.toggle(0)
        self.assertTrue(router.toggle(1))
        self.assertFalse(router.ground)

    def test_deflected_switch_requires_new_press(self):
        router = self.router()
        router.value = 65534
        self.assertFalse(router.toggle(1))
        router.value = 32767
        self.assertFalse(router.toggle(1))
        router.toggle(0)
        self.assertTrue(router.toggle(1))

    def test_maintained_switch_tracks_both_positions(self):
        router = self.router()
        router.maintained = True
        self.assertTrue(router.toggle(1))
        self.assertTrue(router.ground)
        self.assertFalse(router.toggle(1))
        self.assertTrue(router.toggle(0))
        self.assertFalse(router.ground)

    def test_maintained_switch_defers_until_center(self):
        router = self.router()
        router.maintained = True
        router.value = 65534
        self.assertFalse(router.toggle(1))
        self.assertFalse(router.ground)
        router.value = 32767
        self.assertTrue(router.apply_requested())
        self.assertTrue(router.ground)

    def test_pending_change_can_be_cancelled(self):
        router = self.router()
        router.maintained = True
        router.value = 65534
        router.toggle(1)
        router.toggle(0)
        router.value = 32767
        self.assertFalse(router.apply_requested())
        self.assertFalse(router.ground)

    def test_latched_contacts_select_explicit_modes(self):
        router = self.router()
        router.maintained = True
        router.flight_button_code = ecodes.BTN_THUMB
        router.flight_active = True
        self.assertFalse(router.select_position(ecodes.BTN_THUMB, 0))
        self.assertTrue(router.select_position(ecodes.BTN_PINKIE, 1))
        self.assertTrue(router.ground)
        self.assertFalse(router.select_position(ecodes.BTN_PINKIE, 1))
        self.assertFalse(router.select_position(ecodes.BTN_PINKIE, 0))
        self.assertTrue(router.select_position(ecodes.BTN_THUMB, 1))
        self.assertFalse(router.ground)

    def test_latched_invalid_contacts_cancel_pending_change(self):
        router = self.router()
        router.maintained = True
        router.flight_button_code = ecodes.BTN_THUMB
        router.value = 65534
        self.assertFalse(router.select_position(ecodes.BTN_PINKIE, 1))
        self.assertTrue(router.requested_ground)
        router.select_position(ecodes.BTN_THUMB, 1)
        router.value = 32767
        self.assertFalse(router.apply_requested())
        self.assertFalse(router.ground)

    def test_latched_change_waits_for_center(self):
        router = self.router()
        router.maintained = True
        router.flight_button_code = ecodes.BTN_THUMB
        router.value = 65534
        router.select_position(ecodes.BTN_PINKIE, 1)
        self.assertFalse(router.ground)
        router.value = 32767
        self.assertTrue(router.apply_requested())
        self.assertTrue(router.ground)
