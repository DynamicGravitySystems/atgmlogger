from setuptools import setup
from setuptools.command.install import install

requirements = [
    'pyserial >= 3.3',
    # 'RPi.GPIO >= 0.6.3'
]


class PostInstall(install):
    def run(self):
        print("Executing post installation tasks")


setup(
    name='dgs-serial-logger',
    version='0.3.0',
    packages=['atgmlogger'],
    # py_modules=['atgmlogger'],
    url='https://github.com/bradyzp/dgs-serial-logger',
    license='',
    author='Zachery Brady',
    author_email='bradyzp@dynamicgravitysystems.com',
    description='Serial Logging Utility for DGS Advanced Technology Gravity '
                'Meters.',
    install_requires=requirements,
    include_package_data=True,
    # scripts=['atgmlogger/atgmlogger.py']
    entry_points={
        'console_scripts': [
            'atgmlogger = atgmlogger.atgmlogger:run'
        ]
    }
)
