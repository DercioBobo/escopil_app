from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in escopil_app/__init__.py
from escopil_app import __version__ as version

setup(
	name="escopil_app",
	version=version,
	description="Escopil App",
	author="Dércio Bobo",
	author_email="derciobob@gmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
