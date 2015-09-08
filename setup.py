from setuptools import setup

setup(name='pihome',
      version='0.9.0',
      author='Wojciech Sznapka',
      author_email='wojciech@sznapka.pl',
      install_requires=[
            'celery',
            'flask',
            'pika',
            'pymongo',
            'python-crontab>1.9',
            'python-dateutil',
            'python-memcached',
            'pyyaml',
      ])