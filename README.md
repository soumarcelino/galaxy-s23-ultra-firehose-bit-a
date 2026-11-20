# Galaxy S23 Ultra Firehose Loader

Firehose loader for the **Samsung Galaxy S23 Ultra (SM-S918B), BIT A / U10, One UI 9**. Tested in November 2026.

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

#GalaxyS23Ultra #SMS918B #BitA #U10 #OneUI9 #Firehose #QualcommEDL
