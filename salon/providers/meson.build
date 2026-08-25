python_sources = [
  '__init__.py',
  'favourites.py',
  'recents.py',
  'static.py',
  'apps.py',
  'games.py',
  'game_sources.py',
  'external.py',
  'registry.py',
]

foreach f : python_sources
  configure_file(
    input: f,
    output: f,
    copy: true,
    install: true,
    install_dir: moduledir / 'providers',
  )
endforeach
