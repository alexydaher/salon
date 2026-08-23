python_sources = [
  '__init__.py',
  'errors.py',
  'model.py',
  'nowplaying.py',
  'catalog.py',
  'bindings.py',
  'provider.py',
  'sandbox.py',
  'session.py',
  'config.py',
  'focus.py',
  'gamelib.py',
  'launchspec.py',
  'editing.py',
  'osk.py',
  'qr.py',
  'remote.py',
  'ranking.py',
  'siteicon.py',
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
