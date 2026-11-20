# Galaxy S23 Ultra Firehose Loader (SM-S918B)

Latest Firehose loader for the Samsung Galaxy S23 Ultra (SM-S918B), BIT A / U10, One UI 9.

## Setup

On Arch Linux, run the setup script from the project folder.

```sh
./setup.sh
```

## Use

Connect the phone in EDL mode over USB and check the connection.

```sh
./firehose.sh check
```

Save a verified copy of `init_boot.img` in `backups/`.

```sh
./firehose.sh backup-init-boot
```

## License

The scripts and this README use the [MIT License](LICENSE). The bundled Firehose loader is third-party firmware.
