schemas_dir = get_option('datadir') / 'glib-2.0' / 'schemas'

install_data(
  'rocks.salon.Salon.gschema.xml',
  install_dir: schemas_dir,
)

# Compiles gschemas.compiled into the build dir so the app can run
# uninstalled via GSETTINGS_SCHEMA_DIR (see the ./salon dev launcher).
gnome.compile_schemas(build_by_default: true)

desktop_conf = configuration_data()
desktop_conf.set('APP_ID', 'rocks.salon.Salon')

configure_file(
  input: 'rocks.salon.Salon.desktop.in',
  output: 'rocks.salon.Salon.desktop',
  configuration: desktop_conf,
  install: true,
  install_dir: datadir / 'applications',
)

subdir('style')

gnome.compile_resources(
  'salon',
  'salon.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  build_by_default: true,
  source_dir: [meson.current_source_dir(), meson.current_build_dir()],
  dependencies: [gen_tokens_css],
)
