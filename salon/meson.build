# Plain python sources are staged into the build tree with copy: true so
# the uninstalled ./salon dev launcher can run `python3 -m salon.main`
# straight out of the build directory, mirroring what gets installed.
python_sources = [
  '__init__.py',
  'app.py',
  'main.py',
]

foreach f : python_sources
  configure_file(
    input: f,
    output: f,
    copy: true,
    install: true,
    install_dir: moduledir,
  )
endforeach

conf = configuration_data()
conf.set('VERSION', meson.project_version())
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'config.py.in',
  output: 'config.py',
  configuration: conf,
  install: true,
  install_dir: moduledir,
)

subdir('core')
subdir('input')
subdir('services')
subdir('providers')
subdir('ui')
