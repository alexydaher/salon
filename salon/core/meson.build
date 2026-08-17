python_sources = [
  '__init__.py',
  'errors.py',
  'model.py',
  'catalog.py',
  'config.py',
  'launchspec.py',
  'tokens.py',
]

foreach f : python_sources
  configure_file(
    input: f,
    output: f,
    copy: true,
    install: true,
    install_dir: moduledir / 'core',
  )
endforeach
