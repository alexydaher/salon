python_sources = [
  '__init__.py',
  'errors.py',
  'model.py',
  'catalog.py',
  'provider.py',
  'sandbox.py',
  'session.py',
  'config.py',
  'focus.py',
  'launchspec.py',
  'editing.py',
  'osk.py',
  'qr.py',
  'ranking.py',
  'status.py',
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
