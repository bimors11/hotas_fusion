# HOTAS Fusion

HOTAS Fusion menggabungkan Thrustmaster HOTAS Warthog joystick dan throttle menjadi satu virtual joystick Linux bernama `Virtual HOTAS Warthog Combined`.

## Install

Untuk install ke sistem dan otomatis berjalan saat boot (Linux dengan systemd; Debian/Ubuntu, Fedora, atau Arch):

```bash
sudo bash install.sh
```

Installer memasang dependensi melalui package manager, membuat virtual environment di `/opt/hotas-fusion/.venv`, memasang aplikasi, udev rule, dan service systemd, lalu langsung mengaktifkan service. Modul `uinput` dan `joydev` dimuat sekarang dan saat boot. Service berjalan sebagai root untuk mengakses perangkat input dan menunggu sampai joystick serta throttle terhubung. Koneksi internet diperlukan untuk mengunduh dependensi. Jalankan ulang installer dari source terbaru untuk memperbarui instalasi.

Untuk menghentikan autostart:

```bash
sudo systemctl disable --now hotas-fusion.service
```

Untuk development tanpa instalasi sistem:

```bash
cd hotas-fusion
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

Nomor `/dev/input/event*` tidak perlu dikonfigurasi: aplikasi mencari nama perangkat pada setiap startup, termasuk setelah service restart saat perangkat dicabut/dipasang. Nama tidak peka huruf besar/kecil dan spasi atau tanda hubung dinormalisasi. Jika perlu, pilih nama lengkap yang ditampilkan oleh `--list`:

```bash
sudo .venv/bin/python hotas_fusion.py --stick "Thustmaster Joystick - HOTAS Warthog" --throttle "Thrustmaster Throttle - HOTAS Warthog"
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

Service berjalan dengan `--wait`, jadi aman aktif saat boot meskipun joystick belum dicolok. Udev rule akan memanggil service begitu stick atau throttle Warthog terdeteksi. Setelah menjalankan installer, cek status dengan:

```bash
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

## Distribusi ke komputer lain

Salin atau clone seluruh folder proyek, lalu jalankan `sudo bash install.sh` pada komputer tujuan. Tidak ada path home atau nomor event yang perlu diedit. Target membutuhkan Linux dengan systemd, Python 3.9+, dan satu pasang HOTAS Warthog. Jika beberapa perangkat memiliki nama yang sama, aplikasi menolak memilih secara acak.
