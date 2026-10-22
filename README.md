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

## Ground/flight untuk QGroundControl

Fitur ini opsional dan selalu mulai dalam **flight** setelah startup/restart. Lihat nama tombol fisik terlebih dahulu:

```bash
sudo .venv/bin/python hotas_fusion.py --dry-run
```

Contoh memakai tombol `BTN_PINKIE` pada stick (pastikan tersedia pada output mapping):

```bash
sudo .venv/bin/python hotas_fusion.py --mode-button BTN_PINKIE
```

Untuk tombol throttle tambahkan `--mode-button-device throttle`. Tekan sekali untuk ground, tekan lagi untuk flight. Perubahan hanya diterima saat stick X berada dalam 5% dari tengah; jika ditolak, pusatkan stick lalu lepas dan tekan tombol lagi. Tombol mode tidak diteruskan ke QGC; penomoran tombol lain tetap. Mode aktif tercatat pada log.

- Flight: stick X menggerakkan virtual `ABS_X` (roll); virtual `ABS_RX` (yaw) netral.
- Ground: stick X menggerakkan virtual `ABS_RX` (yaw); virtual `ABS_X` (roll) netral.
- Pitch dan throttle tetap. Tidak ada kontrol roll dan yaw secara bersamaan.

Kalibrasi ulang joystick di QGC setelah mengaktifkan fitur ini. Untuk langkah roll, gunakan flight; untuk yaw, pusatkan stick, pindah ke ground, lalu gerakkan stick X. QGC mungkin menampilkan nomor axis, bukan nama ABS; identifikasi melalui monitor axis. Kembali ke flight setelah kalibrasi. Mode ini hanya routing kontrol, tidak mengubah flight mode autopilot atau mendeteksi pesawat di darat.

Agar service memakai fitur ini, jalankan `sudo systemctl edit hotas-fusion.service` dan isi:

```ini
[Service]
ExecStart=
ExecStart=/opt/hotas-fusion/.venv/bin/python -u /opt/hotas-fusion/hotas_fusion.py --wait --mode-button BTN_PINKIE
```

Kemudian jalankan `sudo systemctl daemon-reload` dan `sudo systemctl restart hotas-fusion.service`. Ganti nama tombol sesuai perangkat Anda. Jangan jalankan instance manual bersamaan dengan service. Uji monitor QGC dan simulator sebelum penggunaan pada kendaraan.

### Switch latching throttle 12/13 (konfigurasi service default)

Service bawaan memakai **button 12 untuk ground** dan **button 13 untuk flight**, mengikuti label zero-based pada joystick tester throttle fisik. Posisi switch menentukan mode, bukan jumlah penekanan.

```bash
sudo .venv/bin/python hotas_fusion.py --ground-button-index 12 --flight-button-index 13
```

Startup membaca posisi switch. Tepat satu kontak harus aktif; jika keduanya mati/aktif saat startup, aplikasi menolak berjalan sampai posisi valid (service akan mencoba lagi). Saat operasi, posisi baru menunggu stick X berada dalam 5% dari tengah. Selama perpindahan kontak atau kontak tidak valid, mode terakhir dipertahankan dan permintaan tertunda dibatalkan. Kedua tombol dikonsumsi lokal, tidak diteruskan ke QGC. Mode aktif dicatat di log.

Jalankan ulang `sudo bash install.sh` untuk memasang service terbaru. Jika sebelumnya membuat override `ExecStart` dengan `systemctl edit`, ganti argumen mode lama dengan `--ground-button-index 12 --flight-button-index 13`. Override mengalahkan service bawaan. Mapping index membutuhkan modul `joydev`, yang dimuat installer. Periksa kedua posisi pada monitor axis QGC sebelum digunakan.
