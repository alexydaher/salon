project(
  'salon',
  version: '0.2.8',
  meson_version: '>= 1.3.0',
)

minimum = import('keyval').load('build-aux/minimum-versions.ini')
python = import('python')
py_installation = python.find_installation('python3', modules: ['gi'])
if not py_installation.language_version().version_compare('>= ' + minimum['python'])
  error('Salon requires Python ' + minimum['python'] + ' or newer')
endif

dependency('gtk4', version: '>= ' + minimum['gtk4'])
dependency('libadwaita-1', version: '>= ' + minimum['libadwaita'])
dependency('gio-2.0', version: '>= ' + minimum['glib'])
dependency('gdk-pixbuf-2.0', version: '>= ' + minimum['gdk_pixbuf'])
dependency('libsoup-3.0', version: '>= ' + minimum['libsoup'])
dependency('manette-0.2', version: '>= ' + minimum['libmanette'])

gnome = import('gnome')

prefix = get_option('prefix')
datadir = prefix / get_option('datadir')
pkgdatadir = datadir / meson.project_name()
moduledir = pkgdatadir / 'salon'

subdir('bin')
subdir('data')
subdir('salon')

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
