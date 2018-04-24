# setup.py for atgmlogger
#
# (C) 2016-2018 Zachery Brady


from setuptools import setup
from atgmlogger import __version__, __description__

requirements = [
    'setuptools >= 38.5.1',
    'pyserial >= 3.3',
    'RPi.GPIO >= 0.6.3'
]

setup(
    name='atgmlogger',
    version=__version__,
    packages=['atgmlogger', 'atgmlogger.plugins', 'atgmlogger.tests',
              'atgmlogger.tests.plugins'],
    url='https://github.com/bradyzp/dgs-serial-logger',
    license='',
    author='Zachery Brady',
    author_email='bradyzp@dynamicgravitysystems.com',
    description="Serial Data Recording Utility for Linux/RaspberryPi devices.",
    long_description=__description__,
    install_requires=requirements,
    python_requires='>=3.5.*',
    include_package_data=True,
    zip_safe=True,
    entry_points={
        'console_scripts': [
            'atgmlogger = atgmlogger.__main__:entry_point'
        ]
    },
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Science/Research',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Scientific/Engineering :: GIS',
        'Topic :: Terminals :: Serial',
        'Topic :: Utilities'
    ]
)
