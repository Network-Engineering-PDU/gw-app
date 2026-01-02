import re
import setuptools

with open("ttgateway/config.py") as f:
    version = re.search(r"VERSION = \"(.*?)\"", f.read()).group(1)

with open("ttgateway/config.py") as f:
    lib_version = re.search(r"LIB_VERSION = \"(.*?)\"", f.read()).group(1)

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ttgateway",
    version=version,
    author="Tychetools",
    description="Tychetools command line app to manage a gateway",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://bitbucket.org/tychetools/gw-app/src/master/",
    packages=setuptools.find_packages(),
    package_data={
        "ttgateway": ["model_data/*"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
    python_requires=">=3.7",
    install_requires=[
        "cmd2==2.4.1",
        "requests==2.27.1",
        "websockets==10.2",
        f"ttgwlib=={lib_version}",
    ],
    extras_require={
        "raft": ["ttraft==1.0.0"],
    },
    entry_points={
        "console_scripts": {
            "ttcli = ttgateway.__init__:cli",
            "ttdaemon = ttgateway.__init__:daemon",
            "ttcli_remote = ttgateway.__init__:remote_cli",
            "ttdiagnosis = ttgateway.__init__:diagnosis",
        }
    },
    scripts=[
        "scripts/ttlog",
        "scripts/ttwatchdog",
        "scripts/ttjson_to_sqlite",
        "scripts/ttsqlite_to_json",
    ]
)
