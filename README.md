# psbody-mesh-build-script

>
> I am here to do science, not to type commands!
> 

[![installation test](https://github.com/johnbanq/psbody-mesh-build-script/actions/workflows/test.yml/badge.svg)](https://github.com/johnbanq/psbody-mesh-build-script/actions/workflows/test.yml)

The (probably) one-key automated build &amp; install script for MPI-IS/mesh

## Usage

just go into your conda environment and run this:
```shell
python -c "import urllib.request ; urllib.request.urlretrieve('https://github.com/johnbanq/psbody-mesh-build-script/releases/latest/download/install_psbody.pyz', 'install_psbody.pyz')" && python install_psbody.pyz
```

this will:
* install a cxx compiler & related dependencies in the environment to build the library
* build the library
* run the automated test

note: this script automatically handles the nstallation issue of pyopengl on windows, so you can use MeshViewer out of the box.

## Prerequisites

This script can only be executed in a conda environment, so you need conda.

This script is only tested on python 3.5-3.9 and on windows & ubuntu (see github actions)

## Other Stuff

>
> author's ramble:
> 
> before you ask, yes, I tried turning it into a conda package.
> But after [herculean effort](https://github.com/johnbanq/psbody-mesh-unofficial-feedstock) I just can't get it to work.
> 
> So I did the next best thing - writing an automated installation script.
> 
> Hope this can be helpful to you and the excruciating pain I had to endure to pull this off is not for nothing......
> 



## License

MIT