# HOTAS Fusion

HOTAS Fusion menggabungkan Thrustmaster HOTAS Warthog joystick dan throttle menjadi satu virtual joystick Linux bernama `Virtual HOTAS Warthog Combined`.

## Install

```bash
cd /home/beta-dev/xperiment/hotas-fusion
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Cek mapping

```bash
.venv/bin/python hotas_fusion.py --dry-run
```

Script auto-detect device berikut:

- `Thustmaster Joystick - HOTAS Warthog`
- `Thrustmaster Throttle - HOTAS Warthog`

Jika auto-detect gagal, lihat semua input device:

```bash
.venv/bin/python hotas_fusion.py --list
```

Lalu jalankan dengan path eksplisit:

```bash
sudo .venv/bin/python hotas_fusion.py --stick /dev/input/event25 --throttle /dev/input/event26
```

## Run manual

```bash
sudo .venv/bin/python hotas_fusion.py
```

Secara default script melakukan grab ke joystick dan throttle fisik agar aplikasi lain hanya menerima input dari virtual joystick. Untuk membiarkan device fisik tetap aktif:

```bash
sudo .venv/bin/python hotas_fusion.py --no-grab
```

Sinyal yang sebelumnya muncul di label `Axis 7` pada `jstest-gtk` dipindahkan ke label `Axis 6` dan memakai soft-ramp default 1.5 detik. Axis ramp dipaksa menjadi range analog centered `-16383..16383`, jadi posisi netral berada di tengah dan input tombol/hat tidak loncat langsung ke maksimum. Untuk mengubah durasi:

```bash
sudo .venv/bin/python hotas_fusion.py --axis7-ramp-time 2.5
```

Untuk mematikan logic ramp axis 6/7:

```bash
sudo .venv/bin/python hotas_fusion.py --no-axis7-ramp
```

## Service systemd

Service berjalan dengan `--wait`, jadi aman aktif saat boot meskipun joystick belum dicolok. Udev rule akan memanggil service begitu stick atau throttle Warthog terdeteksi.

```bash
sudo cp systemd/hotas-fusion.service /etc/systemd/system/
sudo cp udev/99-hotas-fusion.rules /etc/udev/rules.d/
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=input
sudo systemctl enable --now hotas-fusion.service
sudo systemctl status hotas-fusion.service
```

Log service:

```bash
journalctl -u hotas-fusion.service -f
```

## Troubleshooting

Jika muncul error `"/dev/uinput" cannot be opened for writing`, jalankan dengan `sudo` atau lewat service systemd. Virtual joystick membutuhkan akses tulis ke `/dev/uinput`, sedangkan input fisik membutuhkan akses baca ke `/dev/input/event*`.

Untuk verifikasi virtual device:

```bash
grep -A5 -B2 "Virtual HOTAS Warthog Combined" /proc/bus/input/devices
```
