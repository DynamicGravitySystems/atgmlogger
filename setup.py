from setuptools import setup
from atgmlogger import __version__, __description__

requirements = [
    'pyserial >= 3.3',
    # 'RPi.GPIO >= 0.6.3'
]

setup(
    name='atgmlogger',
    version=__version__,
    packages=['atgmlogger', 'atgmlogger.plugins', 'test', 'test.plugins'],
    url='https://github.com/bradyzp/dgs-serial-logger',
    license='',
    author='Zachery Brady',
    author_email='bradyzp@dynamicgravitysystems.com',
    description=__description__,
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
    tests_require=['pytest']
)
