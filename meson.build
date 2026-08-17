project(
  'salon',
  version: '0.1.0',
  meson_version: '>= 1.3.0',
)

python = import('python')
py_installation = python.find_installation('python3', modules: ['gi'])

gnome = import('gnome')

prefix = get_option('prefix')
datadir = prefix / get_option('datadir')
pkgdatadir = datadir / meson.project_name()
moduledir = pkgdatadir / 'salon'

subdir('data')
subdir('salon')

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
