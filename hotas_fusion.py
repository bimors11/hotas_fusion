#!/usr/bin/env python3
"""Merge Thrustmaster HOTAS Warthog stick and throttle into one uinput device."""

from __future__ import annotations

import argparse
import logging
import select
import signal
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from evdev import AbsInfo, InputDevice, UInput, ecodes, list_devices


LOGGER = logging.getLogger("hotas-fusion")
VIRTUAL_NAME = "Virtual HOTAS Warthog Combined"
STICK_TOKENS = ("joystick", "hotas warthog")
THROTTLE_TOKENS = ("throttle", "hotas warthog")
RAMP_AXIS_CODES = {ecodes.ABS_THROTTLE, ecodes.ABS_RUDDER, ecodes.ABS_GAS}
RAMP_AXIS_MIN = -16383
RAMP_AXIS_MAX = 16383


@dataclass(frozen=True)
class SourceDevice:
    role: str
    device: InputDevice


@dataclass
class RampState:
    value: float
    target: float
    min_value: int
    max_value: int
    last_update: float


def code_name(code_type: int, code: int) -> str:
    name = ecodes.bytype.get(code_type, {}).get(code, str(code))
    if isinstance(name, (list, tuple)):
        return name[0]
    return str(name)


def abs_tuple(info: AbsInfo) -> Tuple[int, int, int, int, int, int]:
    return (info.value, info.min, info.max, info.fuzz, info.flat, info.resolution)


def normalize_name(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def find_device(tokens: Sequence[str], device_name: Optional[str] = None) -> InputDevice:
    """Resolve a device name on every scan; event numbers are never configuration."""
    matches: List[InputDevice] = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except OSError:
            # Devices can disappear between enumeration and opening.
            continue
        name = normalize_name(dev.name)
        matches_name = (name == normalize_name(device_name)) if device_name else all(token in name for token in tokens)
        if matches_name:
            matches.append(dev)
        else:
            dev.close()

    if not matches:
        token_text = device_name or ", ".join(tokens)
        raise RuntimeError(f"device dengan token [{token_text}] tidak ditemukan")
    if len(matches) > 1:
        choices = ", ".join(f"{dev.path} ({dev.name})" for dev in matches)
        for dev in matches:
            dev.close()
        raise RuntimeError(f"lebih dari satu device cocok: {choices}")
    return matches[0]


def open_sources(args: argparse.Namespace) -> List[SourceDevice]:
    stick = find_device(STICK_TOKENS, args.stick)
    try:
        throttle = find_device(THROTTLE_TOKENS, args.throttle)
    except Exception:
        stick.close()
        raise
    return [SourceDevice("stick", stick), SourceDevice("throttle", throttle)]


def wait_for_sources(args: argparse.Namespace) -> List[SourceDevice]:
    while True:
        try:
            return open_sources(args)
        except RuntimeError as exc:
            LOGGER.info("%s; menunggu HOTAS Warthog lengkap...", exc)
            time.sleep(args.wait_interval)


def source_abs_caps(source: SourceDevice) -> Mapping[int, AbsInfo]:
    caps = source.device.capabilities(absinfo=True)
    result: Dict[int, AbsInfo] = {}
    for code, info in caps.get(ecodes.EV_ABS, []):
        result[code] = info
    return result


def source_key_caps(source: SourceDevice) -> List[int]:
    caps = source.device.capabilities(absinfo=False)
    return sorted(caps.get(ecodes.EV_KEY, []))


def source_abs_ranges(sources: Sequence[SourceDevice]) -> Dict[Tuple[str, int], Tuple[int, int]]:
    ranges: Dict[Tuple[str, int], Tuple[int, int]] = {}
    for source in sources:
        for code, info in source_abs_caps(source).items():
            ranges[(source.role, code)] = (info.min, info.max)
    return ranges


def default_axis_map(role: str) -> Dict[int, int]:
    if role == "stick":
        return {
            ecodes.ABS_X: ecodes.ABS_X,
            ecodes.ABS_Y: ecodes.ABS_Y,
            ecodes.ABS_HAT0X: ecodes.ABS_GAS,
            ecodes.ABS_HAT0Y: ecodes.ABS_HAT0Y,
        }

    return {
        ecodes.ABS_X: ecodes.ABS_Z,
        ecodes.ABS_Y: ecodes.ABS_RZ,
        ecodes.ABS_Z: ecodes.ABS_THROTTLE,
        ecodes.ABS_RZ: ecodes.ABS_RUDDER,
        ecodes.ABS_THROTTLE: ecodes.ABS_HAT0X,
        ecodes.ABS_HAT0X: ecodes.ABS_HAT1X,
        ecodes.ABS_HAT0Y: ecodes.ABS_HAT1Y,
    }


def output_button_codes(total: int) -> List[int]:
    preferred = [
        ecodes.BTN_TRIGGER,
        ecodes.BTN_THUMB,
        ecodes.BTN_THUMB2,
        ecodes.BTN_TOP,
        ecodes.BTN_TOP2,
        ecodes.BTN_PINKIE,
        ecodes.BTN_BASE,
        ecodes.BTN_BASE2,
        ecodes.BTN_BASE3,
        ecodes.BTN_BASE4,
        ecodes.BTN_BASE5,
        ecodes.BTN_BASE6,
    ]
    preferred.extend(range(ecodes.BTN_TRIGGER_HAPPY1, ecodes.BTN_TRIGGER_HAPPY40 + 1))
    if total > len(preferred):
        raise RuntimeError(
            f"terlalu banyak tombol ({total}); kernel hanya menyediakan {len(preferred)} kode joystick standar"
        )
    return preferred[:total]


def build_maps(sources: Sequence[SourceDevice]) -> Tuple[Dict[Tuple[str, int], int], Dict[Tuple[str, int], int]]:
    axis_map: Dict[Tuple[str, int], int] = {}
    for source in sources:
        available = source_abs_caps(source)
        for src_code, dst_code in default_axis_map(source.role).items():
            if src_code in available:
                axis_map[(source.role, src_code)] = dst_code

    key_pairs: List[Tuple[str, int]] = []
    for source in sources:
        for code in source_key_caps(source):
            if code >= ecodes.BTN_MISC:
                key_pairs.append((source.role, code))

    key_map = {pair: dst for pair, dst in zip(key_pairs, output_button_codes(len(key_pairs)))}
    return axis_map, key_map


def build_virtual_abs_caps(
    sources: Sequence[SourceDevice],
    axis_map: Mapping[Tuple[str, int], int],
    ramped_axes: Set[int],
) -> Dict[int, Tuple[int, int, int, int, int, int]]:
    abs_caps: Dict[int, Tuple[int, int, int, int, int, int]] = {}
    for source in sources:
        available = source_abs_caps(source)
        for src_code, dst_code in axis_map.items():
            role, code = src_code
            if role == source.role and code in available:
                value, min_value, max_value, fuzz, flat, resolution = abs_tuple(available[code])
                if dst_code in ramped_axes:
                    value = RAMP_AXIS_MIN
                    min_value = RAMP_AXIS_MIN
                    max_value = RAMP_AXIS_MAX
                    fuzz = 0
                    flat = 0
                abs_caps[dst_code] = (value, min_value, max_value, fuzz, flat, resolution)
    return abs_caps


def create_virtual_device(
    sources: Sequence[SourceDevice],
    axis_map: Mapping[Tuple[str, int], int],
    key_map: Mapping[Tuple[str, int], int],
    ramped_axes: Set[int],
) -> UInput:
    abs_caps = build_virtual_abs_caps(sources, axis_map, ramped_axes)

    capabilities = {
        ecodes.EV_KEY: sorted(set(key_map.values())),
        ecodes.EV_ABS: sorted(abs_caps.items()),
    }
    return UInput(capabilities, name=VIRTUAL_NAME, bustype=ecodes.BUS_USB, vendor=0x044F, product=0xBEEF)


def create_ramp_states(
    abs_caps: Mapping[int, Tuple[int, int, int, int, int, int]],
    ramped_axes: Set[int],
) -> Dict[int, RampState]:
    now = time.monotonic()
    states: Dict[int, RampState] = {}
    for code in ramped_axes:
        if code not in abs_caps:
            continue
        value, min_value, max_value, _fuzz, _flat, _resolution = abs_caps[code]
        states[code] = RampState(
            value=float(value),
            target=float(value),
            min_value=min_value,
            max_value=max_value,
            last_update=now,
        )
    return states


def update_ramp_state(state: RampState, now: float, ramp_time: float) -> int:
    elapsed = max(0.0, now - state.last_update)
    state.last_update = now

    if ramp_time <= 0:
        state.value = state.target
        return int(round(state.value))

    full_range = max(1, abs(state.max_value - state.min_value))
    step = full_range * elapsed / ramp_time
    delta = state.target - state.value
    if abs(delta) <= step:
        state.value = state.target
    elif delta > 0:
        state.value += step
    else:
        state.value -= step
    return int(round(state.value))


def has_active_ramp(ramp_states: Mapping[int, RampState]) -> bool:
    return any(round(state.value) != round(state.target) for state in ramp_states.values())


def scale_to_ramp_target(
    value: int,
    src_min: int,
    src_max: int,
    dst_min: int,
    dst_max: int,
) -> float:
    if src_max == src_min:
        return float(dst_max if value else (dst_min + dst_max) / 2)

    normalized = (value - src_min) / (src_max - src_min)
    normalized = max(0.0, min(1.0, normalized))

    return float(dst_min + normalized * (dst_max - dst_min))


def print_mapping(
    sources: Sequence[SourceDevice],
    axis_map: Mapping[Tuple[str, int], int],
    key_map: Mapping[Tuple[str, int], int],
) -> None:
    for source in sources:
        print(f"{source.role}: {source.device.path} - {source.device.name}")

    print("\nAxis map:")
    for (role, src), dst in sorted(axis_map.items()):
        print(f"  {role:8s} {code_name(ecodes.EV_ABS, src):14s} -> {code_name(ecodes.EV_ABS, dst)}")

    print("\nButton map:")
    for (role, src), dst in sorted(key_map.items()):
        print(f"  {role:8s} {code_name(ecodes.EV_KEY, src):18s} -> {code_name(ecodes.EV_KEY, dst)}")


def relay_events(
    sources: Sequence[SourceDevice],
    virtual: UInput,
    axis_map: Mapping[Tuple[str, int], int],
    key_map: Mapping[Tuple[str, int], int],
    ramp_states: Mapping[int, RampState],
    source_ranges: Mapping[Tuple[str, int], Tuple[int, int]],
    axis_ramp_time: float,
) -> None:
    devices = {source.device.fd: source for source in sources}
    running = True

    def stop(_signum, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    while running:
        timeout = 0.02 if has_active_ramp(ramp_states) else 0.5
        readable, _, _ = select.select(list(devices), [], [], timeout)
        for fd in readable:
            source = devices[fd]
            try:
                events = source.device.read()
            except OSError as exc:
                raise RuntimeError(f"gagal membaca {source.device.path}: {exc}") from exc

            should_sync = False
            for event in events:
                if event.type == ecodes.EV_ABS:
                    dst = axis_map.get((source.role, event.code))
                    if dst is not None:
                        ramp_state = ramp_states.get(dst)
                        if ramp_state is None:
                            virtual.write(ecodes.EV_ABS, dst, event.value)
                        else:
                            src_min, src_max = source_ranges[(source.role, event.code)]
                            ramp_state.target = scale_to_ramp_target(
                                event.value,
                                src_min,
                                src_max,
                                ramp_state.min_value,
                                ramp_state.max_value,
                            )
                        should_sync = True
                elif event.type == ecodes.EV_KEY:
                    dst = key_map.get((source.role, event.code))
                    if dst is not None:
                        virtual.write(ecodes.EV_KEY, dst, event.value)
                        should_sync = True

            if should_sync:
                virtual.syn()

        ramp_synced = False
        now = time.monotonic()
        for code, state in ramp_states.items():
            if round(state.value) == round(state.target):
                continue
            virtual.write(ecodes.EV_ABS, code, update_ramp_state(state, now, axis_ramp_time))
            ramp_synced = True
        if ramp_synced:
            virtual.syn()


def grab_sources(sources: Iterable[SourceDevice]) -> None:
    for source in sources:
        source.device.grab()
        LOGGER.info("grabbed %s (%s)", source.device.path, source.device.name)


def ungrab_sources(sources: Iterable[SourceDevice]) -> None:
    for source in sources:
        try:
            source.device.ungrab()
        except OSError:
            pass


def list_input_devices() -> None:
    for path in list_devices():
        dev = InputDevice(path)
        print(f"{path}: {dev.name}")
        dev.close()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gabungkan HOTAS Warthog joystick dan throttle menjadi satu virtual joystick Linux."
    )
    parser.add_argument("--stick", metavar="NAME", help="Nama lengkap joystick (default: deteksi HOTAS Warthog)")
    parser.add_argument("--throttle", metavar="NAME", help="Nama lengkap throttle (default: deteksi HOTAS Warthog)")
    parser.add_argument("--no-grab", action="store_true", help="Jangan sembunyikan device asli dari aplikasi lain")
    parser.add_argument("--dry-run", action="store_true", help="Tampilkan device dan mapping tanpa membuat uinput")
    parser.add_argument("--list", action="store_true", help="Tampilkan semua input device lalu keluar")
    parser.add_argument("--wait", action="store_true", help="Tunggu sampai joystick dan throttle Warthog terdeteksi")
    parser.add_argument("--wait-interval", type=float, default=2.0, help="Interval polling device untuk --wait")
    parser.add_argument(
        "--axis7-ramp-time",
        type=float,
        default=1.5,
        help="Waktu detik untuk ramp output axis hasil swap, sekarang virtual axis 6/ABS_THROTTLE",
    )
    parser.add_argument("--no-axis7-ramp", action="store_true", help="Matikan soft-ramp untuk output axis hasil swap")
    parser.add_argument("--ramp-both-axes", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.add_argument("--verbose", action="store_true", help="Log lebih detail")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.list:
        list_input_devices()
        return 0

    sources: List[SourceDevice] = []
    virtual: Optional[UInput] = None
    try:
        sources = wait_for_sources(args) if args.wait else open_sources(args)
        axis_map, key_map = build_maps(sources)
        print_mapping(sources, axis_map, key_map)
        ramped_axes = set() if args.no_axis7_ramp else set(RAMP_AXIS_CODES)
        abs_caps = build_virtual_abs_caps(sources, axis_map, ramped_axes)
        ramp_states = create_ramp_states(abs_caps, ramped_axes)
        source_ranges = source_abs_ranges(sources)

        if args.dry_run:
            if ramp_states:
                ramp_names = ", ".join(code_name(ecodes.EV_ABS, code) for code in sorted(ramp_states))
                print(f"\nSoft-ramp: {ramp_names} full-range {args.axis7_ramp_time:.2f}s")
            return 0

        if not args.no_grab:
            grab_sources(sources)

        virtual = create_virtual_device(sources, axis_map, key_map, ramped_axes)
        time.sleep(0.5)
        LOGGER.info("virtual joystick aktif: %s", VIRTUAL_NAME)
        relay_events(sources, virtual, axis_map, key_map, ramp_states, source_ranges, args.axis7_ramp_time)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1
    finally:
        if sources and not args.no_grab:
            ungrab_sources(sources)
        if virtual is not None:
            virtual.close()
        for source in sources:
            source.device.close()


if __name__ == "__main__":
    sys.exit(main())
