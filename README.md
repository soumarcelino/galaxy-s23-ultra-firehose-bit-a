<p align="center">
  <img src="assets/firehose-penguin.png" alt="Firehose Loader EDL Penguin Breakout" width="380">
</p>

# Galaxy S23 Ultra Firehose Loader (SM-S918B)

Latest Firehose loader for the Samsung Galaxy S23 Ultra (SM-S918B), BIT A / U10, One UI 9.

## Install on Arch Linux

Run these commands from the project folder. The first installs the dependencies. The second builds QDL 2.9.1 and installs its USB access rule.

```sh
sudo pacman -S --needed gcc pkgconf git meson ninja libusb libxml2 usbutils python
./setup.sh
```

## How to use

Connect one SM-S918B in EDL mode over USB and check the connection.

```sh
./firehose.sh check
```

### Back up firmware

The 256 GB partition map covers 99 physical partitions across six UFS logical units. The backup reads 38 firmware partitions up to 1 GB each (1,000,000,000 bytes). It skips device-specific data, `userdata`, `system`, `super` and every partition inside `super`.

Choose a new backup folder. The second command verifies the images and lists their positions and sizes.

```sh
python3 partitions.py backup backups/my-s23
python3 partitions.py plan backups/my-s23
```

For a quick copy of `init_boot` alone, run `./firehose.sh backup-init-boot`.

### Rebuild or restore

Rebuild six sparse disk images on the PC from the saved partition tables and firmware. Omitted partitions occupy empty ranges. The command asks you to type `REBUILD SM-S918B`.

```sh
python3 partitions.py rebuild backups/my-s23 rebuilt-disks
```

To restore one partition on the phone, use its name from the plan. Use `ALL` for the full firmware selection. The script checks the connected phone’s partition tables, lists the changes and requires typed confirmation before writing.

```sh
python3 partitions.py restore backups/my-s23 init_boot
```

### Restore an image from the release

Download `sm-s918b-bit-a-firmware-backup.zip` from the release. It contains ten signed firmware images, five partitions verified to contain only zero bytes, and both partition maps. The five empty images record the state of the source phone.

Use the original backup folder from your phone for its partition tables and verification record. To recover a missing `init_boot.img`, run these commands from the project folder with the ZIP in your Downloads directory.

```sh
sudo pacman -S --needed unzip zstd
unzip -n ~/Downloads/sm-s918b-bit-a-firmware-backup.zip -d backups/release
( set -C; zstd -dc backups/release/init_boot.img.zst > backups/my-s23/images/init_boot.img )
python3 partitions.py plan backups/my-s23
python3 partitions.py restore backups/my-s23 init_boot
```

The plan verifies the recovered image against your original backup. If the phone already matches, the script finishes immediately. If a write is needed, review the partition name and type `RESTORE SM-S918B init_boot`. The script checks the result after an accepted write. Hardware testing covered reading and offline reconstruction.

### Downloads and partition maps

The release includes the loader and ten signed firmware images from this backup. The maps list partition names, sizes and offsets. [Release downloads](https://github.com/soumarcelino/galaxy-s23-ultra-firehose-bit-a/releases/tag/2026.11) · [Physical partitions](partitions/physical.csv) · [Logical partitions inside `super`](partitions/logical.csv)

## 🇧🇷 É Brazuca também?

Deixe um apoio usando Pix.

Sua ajuda motiva expandir esse trabalho pra novos devices e é um jeito de
agradecer pelas noites sem dormir por trás desse port.

**Chave Pix:** `de68ce24-a653-4094-9f5c-1504917d14ea`

<p align="center">
  <img src="assets/pix-apoia-o-brazuca.png" alt="QR Code Pix para apoiar o projeto" width="220">
</p>

## License

The scripts and this README use the [MIT License](LICENSE). The bundled Firehose loader is third-party firmware.
