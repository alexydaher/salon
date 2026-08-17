python_sources = [
  '__init__.py',
  'window.py',
  'home.py',
  'tile.py',
]

foreach f : python_sources
  configure_file(
    input: f,
    output: f,
    copy: true,
    install: true,
    install_dir: moduledir / 'ui',
  )
endforeach
