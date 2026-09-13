#!/bin/sh
# El volumen de Fly se monta como root: ajustamos el propietario del directorio de datos
# y bajamos de privilegios antes de arrancar la app. Si ya corremos sin privilegios, no hacemos nada.
set -e

DIR_DATOS="$(dirname "${BP_BD:-/datos/buscaproducto.sqlite}")"

if [ "$(id -u)" = "0" ]; then
  mkdir -p "${DIR_DATOS}"
  chown -R 10001:10001 "${DIR_DATOS}"
  if command -v setpriv > /dev/null 2>&1; then
    exec setpriv --reuid=10001 --regid=10001 --init-groups "$@"
  fi
  if command -v runuser > /dev/null 2>&1; then
    exec runuser -u buscaproducto -- "$@"
  fi
  echo "entrypoint: aviso - sin setpriv ni runuser, se arranca como root"
fi

exec "$@"
