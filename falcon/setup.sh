# Install cockpit
. /etc/os-release
sudo apt install -t ${VERSION_CODENAME}-backports cockpit
sudo apt install cockpit-machines

# Enable cockpit
systemctl enable --now cockpit.socket

# Install virtualization packages
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virtinst

# Add the current user to 'libvirt' and 'kvm' groups for permissions
sudo usermod -aG libvirt,kvm $(whoami)

# Enable and start libvirtd service
sudo systemctl enable --now libvirtd

# Configure network bridge for VMs to access LAN
# Replace 'ens3' with your actual network interface name
NET_IFACE=$(ip route | grep default | awk '{print $5}')
BRIDGE_NAME="br0"

# Create a bridge interface
sudo nmcli connection add type bridge ifname $BRIDGE_NAME autoconnect yes

# Add your network interface to the bridge
sudo nmcli connection add type bridge-slave ifname $NET_IFACE master $BRIDGE_NAME

# Modify the IP configuration to use the bridge
sudo nmcli connection modify $NET_IFACE ipv4.method disabled
sudo nmcli connection modify $BRIDGE_NAME ipv4.method auto

# Restart NetworkManager to apply changes
sudo systemctl restart NetworkManager

# Create a logical volume for VM storage
sudo lvcreate -L 500G -n vm-storage ubuntu-vg

# Format the logical volume as ext4
sudo mkfs.ext4 /dev/ubuntu-vg/vm-storage

# Mount the logical volume to a directory
sudo mkdir -p /var/lib/libvirt/images

# Add the mount point to fstab
echo "/dev/ubuntu-vg/vm-storage /var/lib/libvirt/images ext4 defaults 0 0" | sudo tee -a /etc/fstab

# Mount the logical volume
sudo mount /dev/ubuntu-vg/vm-storage /var/lib/libvirt/images

echo "Configuration is complete. Please reboot your system to apply group membership changes."

## cockpit-file-sharing
curl -sSL https://repo.45drives.com/setup | sudo bash
sudo apt-get update
sudo apt install cockpit-file-sharing
sudo apt install cockpit-identities

## tpu setup from https://coral.ai/docs/m2/get-started/#2a-on-linux

echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list

curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -

sudo apt-get update
sudo apt-get install gasket-dkms libedgetpu1-std

sudo sh -c "echo 'SUBSYSTEM==\"apex\", MODE=\"0660\", GROUP=\"apex\"' >> /etc/udev/rules.d/65-apex.rules"

sudo groupadd apex

sudo adduser $USER apex
