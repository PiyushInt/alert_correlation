#!/bin/bash
# Must be run after every 'colima stop'
echo "Setting up Colima loopback mount for valkey-data..."
colima ssh -- sudo mkdir -p /mnt/valkey-data
colima ssh -- sudo fallocate -l 200M /valkey.img
colima ssh -- sudo mkfs.ext4 -F /valkey.img
colima ssh -- sudo mount -o loop /valkey.img /mnt/valkey-data
colima ssh -- sudo chmod 777 /mnt/valkey-data
echo "Volume setup complete."
