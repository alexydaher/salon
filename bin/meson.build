# The installed launcher. bin/salon (checked in, not installed) is the
# uninstalled dev equivalent; this one is configured with the real
# pkgdatadir and lands in $bindir.
launcher_conf = configuration_data()
launcher_conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'salon.in',
  output: 'salon',
  configuration: launcher_conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
