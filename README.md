# scalez-sensor
## Wifi Manager and Admin Page Setup

Copy the scripts and the admin page to the Raspberry Pi (RPI) using the `scp` command:

```sh
scp -r adminPage network_ap_setup.sh rpi_setup_wo_wifi.sh cloud_control.py scale_reader.py connect_to_wifi.sh wifi-disconnect.sh setup_wifi_manager.sh amitash@192.168.86.24:/home/amitash/
```

Run the following commands on the RPI:
```sh
ssh amitash@[RPI IP]
```

setup the network access point:

```sh
chmod +x network_ap_setup.sh
sudo ./network_ap_setup.sh
```

Setup the wifi manager:
```sh
chmod +x setup_wifi_manager.sh
sudo ./setup_wifi_manager.sh
```

reboot the rpi:
```sh
sudo reboot
```
generate certificate
```python
python certificate-generator.py --scale-id [scale id]
```

upload the certs to the rpi from the wifi manager (from browser -> RPI IP)