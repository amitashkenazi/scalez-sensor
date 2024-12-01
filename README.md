# scalez-sensor
## Wifi Manager and Admin Page Setup

Copy the scripts and the admin page to the Raspberry Pi (RPI) using the `scp` command:

```sh
scp -r adminPage network_ap_setup.sh set_scale_interval.py set_scale_interval.py rpi_setup_wo_wifi.sh cloud_control.py scale_reader.py connect_to_wifi.sh wifi-disconnect.sh setup_wifi_manager.sh amitash@192.168.86.24:/home/amitash/
```

Create new certificate:
```python
python certificate-generator.py --device-id [device-id] --stage prod --policy-name scale-management-system-scale-policy-prod
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

upload the certs to the rpi from the wifi manager (from browser -> RPI IP)


for checking the status of the serices:
```
sudo systemctl status scale-reader
```