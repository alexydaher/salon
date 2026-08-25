python_sources = [
  '__init__.py',
  'context.py',
  'widgets.py',
  'popup.py',
  'panels.py',
  'tiles.py',
  'providers.py',
  'screen.py',
]

foreach f : python_sources
  configure_file(
    input: f,
    output: f,
    copy: true,
    install: true,
    install_dir: moduledir / 'ui' / 'settings',
  )
endforeach
