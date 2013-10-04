# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  # All Vagrant configuration is done here. The configuration options
  # in use are documented and commented below.  For a complete
  # reference, please see the online documentation at vagrantup.com.

  # Every Vagrant virtual environment requires a box to build off of.
  config.vm.box = "precise-server-cloudimg-vagrant-amd64"

  # The url from where the 'config.vm.box' box will be fetched if it
  # doesn't already exist on the user's system.
  config.vm.box_url = "http://cloud-images.ubuntu.com/precise/current/precise-server-cloudimg-vagrant-amd64-disk1.box"

  # --------------------------------------------------------------------------
  # Create a forwarded port mapping which allows access to a specific
  # port within the machine from a port on the host machine.

  # Primary web server (Nginx)
  config.vm.network :forwarded_port, guest: 80, host: 8080

  # Circus web console/dashboard
  config.vm.network :forwarded_port, guest: 8080, host: 8087

  # Direct WSGI server (bypass Nginx)
  config.vm.network :forwarded_port, guest: 8888, host: 8088

  # Create a private network, which allows host-only access to the
  # machine using a specific IP.
  config.vm.network :private_network, ip: "192.168.9.10"

  # Share additional folders to the guest VM. The first argument is
  # the path on the host to the actual folder. The second argument is
  # the path on the guest to mount the folder. And the optional third
  # argument is a set of non-required options.
  config.vm.synced_folder ".", "/srv/councilroom_src"

  # Provider-specific configuration so you can fine-tune various
  # backing providers for Vagrant. These expose provider-specific
  # options.
  config.vm.provider :virtualbox do |vb|
    # Default is to boot in a headless mode:
    vb.gui = false

    # Use VBoxManage to customize the VM. For example to change
    # memory:
    vb.customize ["modifyvm", :id, "--memory", "1024"]
  end

  # Provision the host as needed.
  config.vm.provision :ansible do |ansible|
    ansible.playbook = "ansible/site.yml"
    ansible.inventory_path = "ansible/development"
  end

end
