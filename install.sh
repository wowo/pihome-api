#!/bin/bash

set -xe

### aliases
echo 'alias ll="ls -lah"' >> ~/.bashrc
source ~/.bashrc

### timezone
sudo timedatectl set-timezone 'Europe/Warsaw'

### static ip
sudo echo 'interface enxb827eb5acd7d
static ip_address=192.168.254.9/24
static routers=192.168.254.254
static domain_name_servers=8.8.8.8 8.8.4.4

interface wlan0
static ip_address=192.168.254.19/24
static routers=192.168.254.254
static domain_name_servers=8.8.8.8 8.8.4.4' >> /etc/dhcpcd.conf
sudo service dhcpcd restart

### copy configs
# scp -r conf/* pi@192.168.254.9:.
# scp -r ~/Development/pihome/dist/* pi@192.168.254.9:/var/www/pihome

### packages
sudo apt install -y nginx git byobu redis vim npm multitail nmap libdata-validate-ip-perl

### byobu
byobu-enable

### pihome-api
cd /var/www/pihome-api
git clone git@github.com:wowo/pihome-api.git .
mv ~/config.yml /var/www/pihome-api/
mv ~/htpasswd /var/www/pihome-api/
pip install -r requirements.txt
echo '*/10 * * * * pi cd /var/www/pihome-api/ && /usr/bin/python pihome.py --store-sensors | tee -a /tmp/cron.log' | sudo tee -a /etc/crontab
echo '* * * * * pi cd /var/www/pihome-api/ && /usr/bin/python pihome.py --cache-sensors | tee -a /tmp/cron.log' | sudo tee -a /etc/crontab
sudo ln -s /home/pi/.local/bin/celery /usr/local/bin/celery

sudo mkdir /var/www/pihome-api /var/www/pihome
sudo chown pi:pi pihome*

sudo ln -s /var/www/pihome-api/mqtt2redis.py /usr/local/bin/mqtt2redis.py
sudo ln -s /var/www/pihome-api/conf/systemd/gunicorn.service /etc/systemd/system/gunicorn.service
sudo ln -s /var/www/pihome-api/conf/systemd/celery_pihome.service /etc/systemd/system/celery_pihome.service
sudo ln -s /var/www/pihome-api/conf/systemd/zigbee2mqtt.service /etc/systemd/system/zigbee2mqtt.service
sudo ln -s /var/www/pihome-api/conf/systemd/mqtt2redis.service /etc/systemd/system/mqtt2redis.service

sudo systemctl enable zigbee2mqtt.service
sudo systemctl enable mqtt2redis.service
sudo systemctl enable celery_pihome.service
sudo systemctl enable gunicorn.service

sudo service zigbee2mqtt start
sudo service mqtt2redis start
sudo service celery_pihome start
sudo service gunicorn start

sudo ln -s /var/www/pihome-api/conf/conf/python.wsgi.conf /etc/nginx/sites-enabled/python
sudo service nginx restart

### gpio
sudo modprobe w1-gpio
sudo modprobe w1-therm
sudo echo 'w1-gpio' >> /etc/modules
sudo echo 'w1-therm' >> /etc/modules
sudo sed -i 's/^dtoverlay=.*$/dtoverlay=w1-gpio-pullup,gpiopin=4/g' /boot/config.txt

### noip
cp ~/no-ip2.conf /tmp/no-ip2.conf
cd /usr/local/src
sudo wget http://www.no-ip.com/client/linux/noip-duc-linux.tar.gz
sudo tar xzf noip-duc-linux.tar.gz
sudo cd no-ip-2.1.9
sudo make
sudo make install

### ddclient

### reboot 
sudo reboot now


