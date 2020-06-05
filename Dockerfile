FROM python:3.8
LABEL Maintainer="Cliff Martin"

LABEL Description="This image is used to start a script that will monitor certain events on 433,92 Mhz" Version="1.0"

# Install additional modules
RUN pip3 install paho-mqtt

# packages needed to compile rtl_433
RUN apt-get update && apt-get install -y \
	rtl-sdr \
	librtlsdr-dev \
	librtlsdr0 \
	git \
	automake \
	libtool \
	cmake

# Pull RTL_433 source code from GIT, compile it and install it
RUN git clone https://github.com/merbanan/rtl_433.git \
	&& cd rtl_433/ \
	&& mkdir build \
	&& cd build \
	&& cmake ../ \
	&& make \
	&& make install


# Copy config, script and make it executable
# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

COPY rtl_433.conf /app
COPY rtl2mqtt.py /app
COPY config.py /app
RUN chmod +x /app/rtl2mqtt.py


# When running a container this script will be executed
ENTRYPOINT ["/app/rtl2mqtt.py"]
