#!/bin/sh
# Publish the site to raffaele.isti.cnr.it (served from ~/public_html on hpc.isti.cnr.it).
# Needs the CNR Pisa VPN (or the ISTI network) and SSH access as raffaele.
# Copies only the public files; old files already on the server are left alone.
set -e
cd "$(dirname "$0")/.."
rsync -av --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  index.html robots.txt sitemap.xml assets \
  raffaele@hpc.isti.cnr.it:public_html/
echo "Published: https://raffaele.isti.cnr.it/"
