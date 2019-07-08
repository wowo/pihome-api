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
sudo apt install -y apache2 git libapache2-mod-wsgi byobu redis vim npm multitail nmap supervisor libdata-validate-ip-perl

### byobu
byobu-enable

### apache 
sudo mv python.wsgi.conf /etc/apache2/sites-available/
sudo a2ensite python.wsgi.conf
sudo mkdir /var/www/pihome-api /var/www/pihome
sudo chown pi:pi pihome*

### pihome-api
cd /var/www/pihome-api
git clone git@github.com:wowo/pihome-api.git .
mv ~/config.yml /var/www/pihome-api/
mv ~/htpasswd /var/www/pihome-api/
pip install -r requirements.txt
sudo service apache2 restart
echo '*/10 * * * * pi cd /var/www/pihome-api/ && /usr/bin/python pihome.py --store-sensors | tee -a /tmp/cron.log' | sudo tee -a /etc/crontab
sudo ln -s /home/pi/.local/bin/celery /usr/local/bin/celery
sudo mv ~/supervisord.conf /etc/supervisor/
sudo service  supervisor restart

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


