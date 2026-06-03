from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="dice-detector",
    version="0.1.0",
    author="Dice Detector",
    description="D&D Dice Detection with Foundry VTT Integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dice-detector/dice-detector",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Games/Entertainment :: Role-Playing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "dice-detector=dice_detector.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "dice_detector": [
            "config/*.yaml",
            "data/*.json",
        ],
    },
)
