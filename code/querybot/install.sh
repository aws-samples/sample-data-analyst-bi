#!/bin/bash

#Install all dependencies
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt
sudo yum install -y iproute
sudo yum install -y jq
sudo yum install -y lsof